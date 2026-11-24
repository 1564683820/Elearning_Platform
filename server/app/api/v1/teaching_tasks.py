"""Teacher-owned task registration and persisted task inspection."""
from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_teacher_id
from app.db.database import get_db
from app.models.teaching_task import TeachingTask
from app.schemas.common import ResponseData
from app.services.teacher_service import TeacherService
from app.services.teaching_task_service import TeachingTaskService
from app.schemas.teaching_task import TeachingArtifact

router = APIRouter(prefix='/teaching-tasks', tags=['教学任务'])


class TaskCreate(BaseModel):
    class_id: int = Field(gt=0)
    objective: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    question_count: int = Field(default=10, ge=1, le=30)
    duration_minutes: int = Field(default=20, ge=5, le=120)


class TaskOut(BaseModel):
    id: str
    class_id: str
    objective: str
    status: str
    checkpoint: dict
    created_at: datetime
    artifact: dict = Field(default_factory=dict)
    artifact_version: int = 0
    approved_version: int | None = None
    published_exam_id: str | None = None
    error_code: str | None = None


def task_out(task: TeachingTask) -> TaskOut:
    return TaskOut(id=str(task.id), class_id=str(task.class_id), objective=task.objective,
                   status=task.status, checkpoint=task.checkpoint, created_at=task.created_at,
                   artifact=task.artifact or {}, artifact_version=task.artifact_version or 0,
                   approved_version=task.approved_version,
                   published_exam_id=str(task.published_exam_id) if task.published_exam_id else None,
                   error_code=task.error_code)


@router.post('', response_model=ResponseData[TaskOut], status_code=201)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db),
                      teacher_id: int = Depends(get_current_teacher_id)):
    try:
        classroom = await TeacherService._verify_class_ownership(db, body.class_id, teacher_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail='班级不存在或不可访问') from error
    if classroom is None:
        raise HTTPException(status_code=404, detail='班级不存在或不可访问')
    task = TeachingTask(teacher_id=teacher_id, class_id=body.class_id,
                        objective=body.objective, status='created', checkpoint={'config': {
                            'question_count': body.question_count, 'duration_minutes': body.duration_minutes}})
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return ResponseData(data=task_out(task))


@router.get('', response_model=ResponseData[list[TaskOut]])
async def list_tasks(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                     db: AsyncSession = Depends(get_db), teacher_id: int = Depends(get_current_teacher_id)):
    from app.models.class_models import ClassTeacher
    result = await db.execute(select(TeachingTask).where(TeachingTask.teacher_id == teacher_id,
                              TeachingTask.class_id.in_(select(ClassTeacher.class_id).where(
                                  ClassTeacher.teacher_id == teacher_id)))
                              .order_by(TeachingTask.created_at.desc(), TeachingTask.id.desc())
                              .offset((page - 1) * page_size).limit(page_size))
    return ResponseData(data=[task_out(task) for task in result.scalars().all()])


@router.get('/{task_id}', response_model=ResponseData[TaskOut])
async def get_task(task_id: int, db: AsyncSession = Depends(get_db),
                   teacher_id: int = Depends(get_current_teacher_id)):
    task = await TeachingTaskService.owned(db, task_id, teacher_id)
    return ResponseData(data=task_out(task))


class VersionRequest(BaseModel):
    version: int = Field(ge=1)


class ArtifactRequest(VersionRequest):
    artifact: TeachingArtifact


@router.put('/{task_id}/artifact', response_model=ResponseData[TaskOut])
async def edit_artifact(task_id: int, body: ArtifactRequest, db: AsyncSession = Depends(get_db),
                        teacher_id: int = Depends(get_current_teacher_id)):
    task = await TeachingTaskService.owned(db, task_id, teacher_id, lock=True)
    await TeachingTaskService.command(db, task, 'artifact', body.version, body.artifact.model_dump())
    return ResponseData(data=task_out(task))


@router.post('/{task_id}/approve', response_model=ResponseData[TaskOut])
async def approve_task(task_id: int, body: VersionRequest, db: AsyncSession = Depends(get_db),
                       teacher_id: int = Depends(get_current_teacher_id)):
    task = await TeachingTaskService.owned(db, task_id, teacher_id, lock=True)
    await TeachingTaskService.command(db, task, 'approve', body.version)
    return ResponseData(data=task_out(task))


@router.post('/{task_id}/publish', response_model=ResponseData[TaskOut])
async def publish_task(task_id: int, body: VersionRequest, db: AsyncSession = Depends(get_db),
                       teacher_id: int = Depends(get_current_teacher_id)):
    task = await TeachingTaskService.owned(db, task_id, teacher_id, lock=True)
    await TeachingTaskService.command(db, task, 'publish', body.version)
    return ResponseData(data=task_out(task))


@router.post('/{task_id}/{action}', response_model=ResponseData[TaskOut])
async def task_command(task_id: int, action: Annotated[str, StringConstraints(pattern='^(run|retry|cancel)$')],
                       db: AsyncSession = Depends(get_db), teacher_id: int = Depends(get_current_teacher_id)):
    task = await TeachingTaskService.owned(db, task_id, teacher_id, lock=True)
    await TeachingTaskService.command(db, task, action)
    return ResponseData(data=task_out(task))


@router.get('/{task_id}/events')
async def task_events(task_id: int, teacher_id: int = Depends(get_current_teacher_id)):
    import asyncio
    from fastapi.responses import StreamingResponse
    from app.db.database import async_session
    async with async_session() as db:
        await TeachingTaskService.owned(db, task_id, teacher_id)

    async def events():
        for _ in range(300):
            async with async_session() as db:
                try:
                    task = await TeachingTaskService.owned(db, task_id, teacher_id)
                except HTTPException:
                    yield 'event: revoked\ndata: {}\n\n'
                    return
                payload = task_out(task).model_dump_json()
                terminal = task.status not in ('queued', 'running')
            yield f'event: task\ndata: {payload}\n\n'
            if terminal:
                return
            await asyncio.sleep(2)

    return StreamingResponse(events(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
