"""Transactional teacher workflow commands; never publish without versioned approval."""
from fastapi import HTTPException
from sqlalchemy import select
from app.models.teaching_task import TeachingTask, TeachingTaskOutbox
from app.models.exam_models import TeacherExam
from app.services.teacher_service import TeacherService
from app.services.exam_service import ExamService
from app.schemas.teaching_task import validate_artifact


class TeachingTaskService:
    @staticmethod
    async def owned(db, task_id: int, teacher_id: int, lock=False):
        query = select(TeachingTask).where(TeachingTask.id == task_id, TeachingTask.teacher_id == teacher_id)
        if lock:
            query = query.with_for_update()
        task = (await db.execute(query)).scalar_one_or_none()
        if task is None:
            raise HTTPException(404, '教学任务不存在')
        try:
            classroom = await TeacherService._verify_class_ownership(db, task.class_id, teacher_id)
        except ValueError as exc:
            raise HTTPException(404, '班级不存在或不可访问') from exc
        if classroom is None:
            raise HTTPException(404, '班级不存在或不可访问')
        return task

    @staticmethod
    async def command(db, task, action: str, expected_version: int | None = None, artifact: dict | None = None):
        if action in ('run', 'retry'):
            allowed = ('created',) if action == 'run' else ('failed', 'awaiting_input')
            if task.status not in allowed:
                raise HTTPException(409, '当前状态不能启动或重试')
            if action == 'retry' and task.status == 'awaiting_input':
                task.checkpoint = {k: v for k, v in task.checkpoint.items() if k == 'config'}
            task.status, task.error_code = 'queued', None
            task.attempts = 0
            db.add(TeachingTaskOutbox(task_id=task.id))
        elif action == 'cancel':
            if task.status in ('published', 'cancelled'):
                raise HTTPException(409, '任务已经结束')
            # Lease fencing prevents an in-flight model response from overwriting cancellation.
            task.status, task.lease_owner, task.lease_until = 'cancelled', None, None
        elif action in ('artifact', 'approve', 'publish'):
            if task.status not in ('awaiting_review', 'approved', 'published'):
                raise HTTPException(409, '任务尚未生成可审核内容')
            if expected_version != task.artifact_version:
                raise HTTPException(409, '内容版本已变化，请刷新后重新审核')
            if action == 'publish' and task.status == 'published':
                return task
            if task.status == 'published':
                raise HTTPException(409, '已发布内容不能修改')
            try:
                validated = validate_artifact(artifact if action == 'artifact' else task.artifact, task.checkpoint)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            if action == 'artifact':
                task.artifact = validated.model_dump()
                task.artifact_version += 1
                task.approved_version, task.status = None, 'awaiting_review'
            elif action == 'approve':
                task.approved_version, task.status = task.artifact_version, 'approved'
            else:
                if task.status != 'approved' or task.approved_version != task.artifact_version:
                    raise HTTPException(409, '请先审核当前版本')
                exam = TeacherExam(teacher_id=task.teacher_id, class_id=task.class_id,
                    title=validated.title, description='教学任务定向巩固练习',
                    questions=[q.model_dump() for q in validated.questions], total_score=validated.total_score,
                    duration_minutes=task.checkpoint.get('config', {}).get('duration_minutes', 20), status='draft')
                db.add(exam)
                await db.flush()
                published = await ExamService.publish_exam(db, exam.id, task.teacher_id, task.class_id)
                if published is None:
                    raise HTTPException(409, '试卷发布失败')
                task.published_exam_id, task.status = exam.id, 'published'
        else:
            raise HTTPException(404, '未知任务操作')
        await db.flush()
        return task
