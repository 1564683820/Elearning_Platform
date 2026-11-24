# 协作增强模块业务逻辑服务
# 助教管理、多教师协作批改、审计日志、学习报告、学校管理、班级学期报告
import json
from datetime import datetime, date, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from app.models.user import User
from app.models.class_models import Class, ClassStudent, ClassTeacher
from app.models.exam_models import TeacherExam, ExamSubmission, ExamGradingLog
from app.models.collaboration_models import AuditLog, SchoolAdmin, LearningReport
from app.models.quiz import WrongQuestion, UserQuizLog
from app.models.stats import UserDailyStat, LearningBehaviorLog
from app.models.word import UserWordProgress
from app.schemas.collaboration import (
    AssistantOut, PersonalReportOut, ClassReportOut,
    AuditLogOut, SchoolAdminOut, SchoolDashboardOut,
)


# ========== 助教/课代表管理 ==========

class AssistantService:
    """助教/课代表管理服务"""

    @staticmethod
    async def add_assistant(
        db: AsyncSession, class_id: int, student_id: int,
        operator_id: int, permissions: Optional[dict] = None,
    ) -> AssistantOut:
        """添加助教/课代表"""
        # 校验操作者是教师
        ct = await db.execute(
            select(ClassTeacher).where(
                ClassTeacher.class_id == class_id,
                ClassTeacher.teacher_id == operator_id,
                ClassTeacher.role == "teacher",
            )
        )
        if not ct.scalar_one_or_none():
            raise ValueError("只有主教师才能添加助教")

        # 校验学生属于该班级
        cs = await db.execute(
            select(ClassStudent).where(
                ClassStudent.class_id == class_id,
                ClassStudent.student_id == student_id,
            )
        )
        if not cs.scalar_one_or_none():
            raise ValueError("该学生不在班级中")

        # 检查是否已是助教/教师
        existing = await db.execute(
            select(ClassTeacher).where(
                ClassTeacher.class_id == class_id,
                ClassTeacher.teacher_id == student_id,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("该用户已在班级中有角色")

        # 添加为助教
        ct_new = ClassTeacher(
            class_id=class_id, teacher_id=student_id,
            role="assistant",
        )
        db.add(ct_new)
        await db.flush()

        # 获取用户信息
        user = await db.get(User, student_id)
        await AuditService.log(
            db=db, class_id=class_id, operator_id=operator_id,
            operator_role="teacher", action_type="assistant_add",
            target_type="assistant", target_id=student_id,
            detail={"permissions": permissions},
        )
        return AssistantOut(
            teacher_id=student_id,
            nickname=user.nickname or "未知",
            role="assistant",
            joined_at=datetime.now(),
        )

    @staticmethod
    async def remove_assistant(
        db: AsyncSession, class_id: int, student_id: int, operator_id: int,
    ) -> bool:
        """移除助教/课代表"""
        ct = await db.execute(
            select(ClassTeacher).where(
                ClassTeacher.class_id == class_id,
                ClassTeacher.teacher_id == operator_id,
                ClassTeacher.role == "teacher",
            )
        )
        if not ct.scalar_one_or_none():
            raise ValueError("只有主教师才能移除助教")

        ct_target = await db.execute(
            select(ClassTeacher).where(
                ClassTeacher.class_id == class_id,
                ClassTeacher.teacher_id == student_id,
                ClassTeacher.role == "assistant",
            )
        )
        target = ct_target.scalar_one_or_none()
        if not target:
            return False

        await db.delete(target)
        await db.flush()
        await AuditService.log(
            db=db, class_id=class_id, operator_id=operator_id,
            operator_role="teacher", action_type="assistant_remove",
            target_type="assistant", target_id=student_id,
        )
        return True

    @staticmethod
    async def list_assistants(
        db: AsyncSession, class_id: int, teacher_id: int,
    ) -> list[AssistantOut]:
        """获取班级的所有助教"""
        ct = await db.execute(
            select(ClassTeacher).where(
                ClassTeacher.class_id == class_id,
                ClassTeacher.teacher_id == teacher_id,
            )
        )
        if not ct.scalar_one_or_none():
            raise ValueError("无权查看该班级")

        stmt = (
            select(ClassTeacher, User.nickname)
            .join(User, User.id == ClassTeacher.teacher_id)
            .where(
                ClassTeacher.class_id == class_id,
                ClassTeacher.role == "assistant",
            )
        )
        result = await db.execute(stmt)
        return [
            AssistantOut(
                teacher_id=row.ClassTeacher.teacher_id,
                nickname=row.nickname or "未知",
                role="assistant",
                joined_at=row.ClassTeacher.joined_at,
            )
            for row in result.all()
        ]

    @staticmethod
    async def update_role(
        db: AsyncSession, class_id: int, target_id: int,
        new_role: str, operator_id: int,
    ):
        """更新班级成员角色（提升/降级）"""
        if new_role not in ("teacher", "assistant"):
            raise ValueError("无效角色")

        ct = await db.execute(
            select(ClassTeacher).where(
                ClassTeacher.class_id == class_id,
                ClassTeacher.teacher_id == operator_id,
                ClassTeacher.role == "teacher",
            )
        )
        if not ct.scalar_one_or_none():
            raise ValueError("只有主教师才能变更角色")

        target = await db.execute(
            select(ClassTeacher).where(
                ClassTeacher.class_id == class_id,
                ClassTeacher.teacher_id == target_id,
            )
        )
        target_row = target.scalar_one_or_none()
        if not target_row:
            raise ValueError("该用户不是班级成员")

        old_role = target_row.role
        target_row.role = new_role
        await db.flush()
        await AuditService.log(
            db=db, class_id=class_id, operator_id=operator_id,
            operator_role="teacher", action_type="role_update",
            target_type="teacher", target_id=target_id,
            detail={"old_role": old_role, "new_role": new_role},
        )


# ========== 多教师协作批改 ==========

class CollaborativeGradingService:
    """多教师协作批改服务"""

    @staticmethod
    async def assign_grading_task(
        db: AsyncSession, submission_id: int,
        grader_id: int, grader_role: str,
        assigned_questions: Optional[list[int]],
        assigner_id: int,
    ):
        """分配批改任务给教师/助教"""
        submission = await db.get(ExamSubmission, submission_id)
        if not submission:
            raise ValueError("提交记录不存在")

        # 记录批改任务到日志
        log = ExamGradingLog(
            submission_id=submission_id,
            grader_type=grader_role,
            grader_id=grader_id,
            action="task_assigned",
            detail={"assigned_questions": assigned_questions, "assigner_id": assigner_id},
        )
        db.add(log)
        await db.flush()
        await AuditService.log(
            db=db, class_id=None, operator_id=assigner_id,
            operator_role="teacher", action_type="grading_task_assign",
            target_type="submission", target_id=submission_id,
            detail={"grader_id": grader_id, "questions": assigned_questions},
        )

    @staticmethod
    async def submit_grading_result(
        db: AsyncSession, submission_id: int,
        grader_id: int, grader_role: str,
        question_scores: list[dict], overall_comment: str,
    ) -> dict:
        """助教/教师提交批改结果"""
        submission = await db.get(ExamSubmission, submission_id)
        if not submission:
            raise ValueError("提交记录不存在")

        # 合并到现有的 teacher_adjustment
        existing = submission.teacher_adjustment or {}
        grader_key = f"{grader_role}_{grader_id}"
        existing[grader_key] = {
            "question_scores": question_scores,
            "overall_comment": overall_comment,
            "submitted_at": datetime.now().isoformat(),
        }
        submission.teacher_adjustment = existing

        # 记录批改日志
        log = ExamGradingLog(
            submission_id=submission_id,
            grader_type=grader_role,
            grader_id=grader_id,
            action="grading_submitted",
            detail={"question_scores": question_scores, "overall_comment": overall_comment},
        )
        db.add(log)
        await db.flush()

        # 如果批改者是主教师，直接完成复核
        if grader_role == "teacher":
            submission.grading_status = "teacher_reviewed"
            await db.flush()

        return {"status": "ok", "grader": grader_key}

    @staticmethod
    async def review_and_finalize(
        db: AsyncSession, submission_id: int,
        adjustments: dict, final_score: int,
        reviewer_id: int,
    ) -> dict:
        """主教师复核并最终确定分数"""
        submission = await db.get(ExamSubmission, submission_id)
        if not submission:
            raise ValueError("提交记录不存在")

        original_score = submission.score or 0
        submission.adjusted_score = final_score
        submission.grading_status = "teacher_reviewed"
        submission.teacher_adjustment = {
            **(submission.teacher_adjustment or {}),
            "final_review": {
                "adjustments": adjustments,
                "reviewed_by": reviewer_id,
                "reviewed_at": datetime.now().isoformat(),
            },
        }
        await db.flush()

        log = ExamGradingLog(
            submission_id=submission_id,
            grader_type="teacher",
            grader_id=reviewer_id,
            action="final_review",
            detail={"original_score": original_score, "final_score": final_score, "adjustments": adjustments},
        )
        db.add(log)
        await db.flush()

        return {
            "submission_id": submission_id,
            "original_score": original_score,
            "adjusted_score": final_score,
        }

    @staticmethod
    async def get_grading_status(
        db: AsyncSession, exam_id: int,
    ) -> list[dict]:
        """获取试卷所有提交的批改进度"""
        stmt = (
            select(ExamSubmission)
            .where(ExamSubmission.exam_id == exam_id)
            .order_by(ExamSubmission.submitted_at)
        )
        result = await db.execute(stmt)
        submissions = result.scalars().all()

        statuses = []
        for sub in submissions:
            logs = await db.execute(
                select(ExamGradingLog)
                .where(ExamGradingLog.submission_id == sub.id)
                .order_by(ExamGradingLog.created_at)
            )
            statuses.append({
                "submission_id": sub.id,
                "student_id": sub.student_id,
                "grading_status": sub.grading_status,
                "score": sub.score,
                "adjusted_score": sub.adjusted_score,
                "log_count": len(logs.all()),
            })
        return statuses


# ========== 审计日志 ==========

class AuditService:
    """操作审计日志服务"""

    @staticmethod
    async def log(
        db: AsyncSession, class_id: Optional[int],
        operator_id: int, operator_role: str,
        action_type: str, target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        detail: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ):
        """记录操作审计日志"""
        log = AuditLog(
            class_id=class_id,
            operator_id=operator_id,
            operator_role=operator_role,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
            ip_address=ip_address,
        )
        db.add(log)
        await db.flush()

    @staticmethod
    async def query(
        db: AsyncSession,
        class_id: Optional[int] = None,
        action_type: Optional[str] = None,
        operator_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """查询审计日志（支持多维度筛选）"""
        query = select(AuditLog)

        filters = []
        if class_id:
            filters.append(AuditLog.class_id == class_id)
        if action_type:
            filters.append(AuditLog.action_type == action_type)
        if operator_id:
            filters.append(AuditLog.operator_id == operator_id)
        if start_date:
            filters.append(func.date(AuditLog.created_at) >= start_date)
        if end_date:
            filters.append(func.date(AuditLog.created_at) <= end_date)

        if filters:
            query = query.where(and_(*filters))

        # 总数
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        # 分页
        query = query.order_by(AuditLog.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        items = result.scalars().all()

        return {
            "items": [AuditLogOut.model_validate(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }


# ========== 学习报告 ==========

class LearningReportService:
    """学习报告生成服务"""

    @staticmethod
    async def generate_personal_report(
        db: AsyncSession, user_id: int,
        class_id: Optional[int] = None,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        words_db: AsyncSession | None = None,
    ) -> PersonalReportOut:
        """生成学生个人学习报告"""
        if not period_end:
            period_end = datetime.now().date()
        if not period_start:
            period_start = period_end - timedelta(days=30)

        user = await db.get(User, user_id)
        nickname = user.nickname if user else ""

        # 学习天数
        days_count = await db.execute(
            select(func.count(func.distinct(func.date(UserDailyStat.date))))
            .where(
                and_(
                    UserDailyStat.user_id == user_id,
                    func.date(UserDailyStat.date) >= period_start,
                    func.date(UserDailyStat.date) <= period_end,
                )
            )
        )
        study_days = days_count.scalar() or 0

        _words_db = words_db or db
        # 单词量
        word_count = await _words_db.execute(
            select(func.count()).where(
                and_(
                    UserWordProgress.user_id == user_id,
                    UserWordProgress.created_at >= period_start,
                )
            )
        )
        total_words = word_count.scalar() or 0

        # 训练统计
        training_count = await db.execute(
            select(func.count()).where(
                and_(
                    UserQuizLog.user_id == user_id,
                    func.date(UserQuizLog.created_at) >= period_start,
                    func.date(UserQuizLog.created_at) <= period_end,
                )
            )
        )
        correct_count = await db.execute(
            select(func.count()).where(
                and_(
                    UserQuizLog.user_id == user_id,
                    UserQuizLog.is_correct == 1,
                    func.date(UserQuizLog.created_at) >= period_start,
                    func.date(UserQuizLog.created_at) <= period_end,
                )
            )
        )
        total_t = training_count.scalar() or 0
        total_c = correct_count.scalar() or 0
        accuracy = round(total_c / total_t * 100, 1) if total_t > 0 else 0.0

        # 考试次数
        exam_count = await db.execute(
            select(func.count()).where(
                and_(
                    ExamSubmission.student_id == user_id,
                    func.date(ExamSubmission.submitted_at) >= period_start,
                    func.date(ExamSubmission.submitted_at) <= period_end,
                )
            )
        )
        total_exams = exam_count.scalar() or 0

        # 各模块正确率
        cat_stmt = (
            select(
                WrongQuestion.category,
                func.count().label("total"),
                func.sum(WrongQuestion.is_mastered == 0).label("wrong"),
            )
            .where(
                and_(
                    WrongQuestion.user_id == user_id,
                    WrongQuestion.category.isnot(None),
                )
            )
            .group_by(WrongQuestion.category)
        )
        cat_result = await db.execute(cat_stmt)
        module_breakdown = []
        for row in cat_result.all():
            t = row.total or 0
            w = row.wrong or 0
            module_breakdown.append({
                "category": row.category,
                "total": t,
                "accuracy": round((t - w) / t * 100, 1) if t > 0 else 0,
            })

        # 薄弱知识点
        weak = await db.execute(
            select(WrongQuestion.knowledge_point, func.count().label("cnt"))
            .where(
                and_(
                    WrongQuestion.user_id == user_id,
                    WrongQuestion.knowledge_point.isnot(None),
                    WrongQuestion.is_mastered == 0,
                )
            )
            .group_by(WrongQuestion.knowledge_point)
            .order_by(func.count().desc())
            .limit(10)
        )
        weakness_points = [
            {"knowledge_point": w[0], "count": w[1]} for w in weak.all()
        ]

        # 每日趋势
        trend = await db.execute(
            select(
                func.date(UserDailyStat.date).label("day"),
                func.sum(UserDailyStat.words_learned).label("words"),
            )
            .where(
                and_(
                    UserDailyStat.user_id == user_id,
                    func.date(UserDailyStat.date) >= period_start,
                    func.date(UserDailyStat.date) <= period_end,
                )
            )
            .group_by(func.date(UserDailyStat.date))
            .order_by(func.date(UserDailyStat.date))
        )
        daily_trend = [
            {"date": str(r.day), "words": r.words or 0}
            for r in trend.all()
        ]

        # 学习建议
        suggestions = LearningReportService._generate_suggestions(
            module_breakdown, weakness_points, accuracy, study_days,
        )

        # 缓存报告
        report = LearningReport(
            user_id=user_id, class_id=class_id,
            report_type="personal",
            period_start=period_start, period_end=period_end,
            report_data={
                "accuracy": accuracy, "total_words": total_words,
                "total_training": total_t, "study_days": study_days,
                "module_breakdown": module_breakdown,
                "weakness_points": weakness_points,
                "suggestions": suggestions,
            },
        )
        db.add(report)

        return PersonalReportOut(
            user_id=user_id, nickname=nickname,
            period_start=period_start, period_end=period_end,
            study_days=study_days, total_words=total_words,
            total_training=total_t, total_exams=total_exams,
            overall_accuracy=accuracy,
            module_breakdown=module_breakdown,
            weakness_points=weakness_points,
            daily_trend=daily_trend,
            improvement_suggestions=suggestions,
        )

    @staticmethod
    async def generate_class_report(
        db: AsyncSession, class_id: int,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        words_db: AsyncSession | None = None,
    ) -> ClassReportOut:
        """生成班级学期报告"""
        if not period_end:
            period_end = datetime.now().date()
        if not period_start:
            period_start = period_end - timedelta(days=90)

        cls = await db.get(Class, class_id)
        if not cls:
            raise ValueError("班级不存在")

        # 获取班级学生
        student_ids_result = await db.execute(
            select(ClassStudent.student_id).where(ClassStudent.class_id == class_id)
        )
        student_ids = [r[0] for r in student_ids_result.all()]
        student_count = len(student_ids)

        if student_count == 0:
            return ClassReportOut(
                class_id=class_id, class_name=cls.name,
                student_count=0, period_start=period_start, period_end=period_end,
            )

        # 整体正确率
        quiz_total = await db.execute(
            select(func.count()).where(
                and_(
                    UserQuizLog.user_id.in_(student_ids),
                    func.date(UserQuizLog.created_at) >= period_start,
                    func.date(UserQuizLog.created_at) <= period_end,
                )
            )
        )
        correct_total = await db.execute(
            select(func.count()).where(
                and_(
                    UserQuizLog.user_id.in_(student_ids),
                    UserQuizLog.is_correct == 1,
                    func.date(UserQuizLog.created_at) >= period_start,
                    func.date(UserQuizLog.created_at) <= period_end,
                )
            )
        )
        total_q = quiz_total.scalar() or 0
        total_c = correct_total.scalar() or 0
        overall_acc = round(total_c / total_q * 100, 1) if total_q > 0 else 0.0

        _words_db = words_db or db
        # 单词量
        word_total = await _words_db.execute(
            select(func.count()).where(
                and_(
                    UserWordProgress.user_id.in_(student_ids),
                    UserWordProgress.created_at >= period_start,
                )
            )
        )

        # 考试数
        exam_count = await db.execute(
            select(func.count(func.distinct(ExamSubmission.exam_id))).where(
                and_(
                    ExamSubmission.student_id.in_(student_ids),
                    func.date(ExamSubmission.submitted_at) >= period_start,
                    func.date(ExamSubmission.submitted_at) <= period_end,
                )
            )
        )

        # 平均学习天数
        avg_days = await db.execute(
            select(
                func.avg(
                    select(func.count(func.distinct(func.date(UserDailyStat.date))))
                    .where(
                        and_(
                            UserDailyStat.user_id.in_(student_ids),
                            func.date(UserDailyStat.date) >= period_start,
                            func.date(UserDailyStat.date) <= period_end,
                        )
                    )
                    .scalar_subquery()
                )
            )
        )

        # 高频错题
        mistakes = await db.execute(
            select(WrongQuestion.knowledge_point, func.count().label("cnt"))
            .where(
                and_(
                    WrongQuestion.user_id.in_(student_ids),
                    WrongQuestion.knowledge_point.isnot(None),
                )
            )
            .group_by(WrongQuestion.knowledge_point)
            .order_by(func.count().desc())
            .limit(5)
        )
        top_mistakes = [
            {"knowledge_point": m[0], "count": m[1]} for m in mistakes.all()
        ]

        # 正确率趋势（按周）
        trend_data = []
        for i in range(12):
            week_start = period_start + timedelta(weeks=i)
            week_end = week_start + timedelta(days=6)
            if week_start > period_end:
                break
            wq = await db.execute(
                select(func.count()).where(
                    and_(
                        UserQuizLog.user_id.in_(student_ids),
                        func.date(UserQuizLog.created_at) >= week_start,
                        func.date(UserQuizLog.created_at) <= min(week_end, period_end),
                    )
                )
            )
            wc = await db.execute(
                select(func.count()).where(
                    and_(
                        UserQuizLog.user_id.in_(student_ids),
                        UserQuizLog.is_correct == 1,
                        func.date(UserQuizLog.created_at) >= week_start,
                        func.date(UserQuizLog.created_at) <= min(week_end, period_end),
                    )
                )
            )
            wq_v = wq.scalar() or 0
            wc_v = wc.scalar() or 0
            if wq_v > 0:
                trend_data.append({
                    "week": week_start.isoformat(),
                    "accuracy": round(wc_v / wq_v * 100, 1),
                    "total": wq_v,
                })

        # 学生排名
        ranking = []
        for sid in student_ids:
            user = await db.get(User, sid)
            sq = await db.execute(
                select(func.count()).where(
                    and_(
                        UserQuizLog.user_id == sid,
                        func.date(UserQuizLog.created_at) >= period_start,
                        func.date(UserQuizLog.created_at) <= period_end,
                    )
                )
            )
            sc = await db.execute(
                select(func.count()).where(
                    and_(
                        UserQuizLog.user_id == sid,
                        UserQuizLog.is_correct == 1,
                        func.date(UserQuizLog.created_at) >= period_start,
                        func.date(UserQuizLog.created_at) <= period_end,
                    )
                )
            )
            sq_v = sq.scalar() or 0
            sc_v = sc.scalar() or 0
            if sq_v > 0:
                ranking.append({
                    "student_id": sid,
                    "name": user.nickname or "未知",
                    "accuracy": round(sc_v / sq_v * 100, 1),
                    "total_quiz": sq_v,
                })

        ranking.sort(key=lambda x: x["accuracy"], reverse=True)

        return ClassReportOut(
            class_id=class_id, class_name=cls.name,
            student_count=student_count,
            period_start=period_start, period_end=period_end,
            overall_accuracy=overall_acc,
            total_words=word_total.scalar() or 0,
            total_exams=exam_count.scalar() or 0,
            total_training=total_q,
            avg_study_days=round(float(avg_days.scalar() or 0), 1),
            top_mistakes=top_mistakes,
            accuracy_trend=trend_data,
            active_trend=[],
            student_ranking=ranking,
        )

    @staticmethod
    def _generate_suggestions(
        module_breakdown: list, weakness_points: list,
        accuracy: float, study_days: int,
    ) -> list[str]:
        """根据学习数据生成 AI 学习建议"""
        suggestions = []

        if accuracy < 60:
            suggestions.append("整体正确率偏低，建议从基础词汇和语法入手，先巩固核心知识点")
        elif accuracy < 80:
            suggestions.append("基础掌握较好，建议针对薄弱知识点进行专项训练")

        if study_days < 7:
            suggestions.append("学习频率较低，建议每天固定时间学习10-15分钟，保持语感")
        elif study_days < 20:
            suggestions.append("学习习惯良好，继续坚持每天学习，可以适当增加训练量")

        weak_categories = [m.get("category") for m in module_breakdown if m.get("accuracy", 100) < 60]
        if "语法" in str(weak_categories) or any("语法" in m.get("category", "") for m in module_breakdown if m.get("accuracy", 100) < 60):
            suggestions.append("语法规整较弱，建议通过情景记忆功能在语境中学习语法规则")

        if weakness_points and len(weakness_points) > 0:
            top_weak = weakness_points[0]["knowledge_point"]
            suggestions.append(f"重点复习「{top_weak}」相关知识点，这是当前最薄弱的环节")

        if not suggestions:
            suggestions.append("整体表现优秀，继续保持！可以尝试更具挑战性的内容")

        return suggestions


# ========== 学校管理 ==========

class SchoolAdminService:
    """学校管理员服务"""

    @staticmethod
    async def create_admin(
        db: AsyncSession, body: dict, creator_id: int,
    ) -> SchoolAdminOut:
        """创建学校管理员"""
        existing = await db.execute(
            select(SchoolAdmin).where(SchoolAdmin.user_id == body["user_id"])
        )
        if existing.scalar_one_or_none():
            raise ValueError("该用户已经是管理员")

        admin = SchoolAdmin(
            user_id=body["user_id"],
            school_name=body["school_name"],
            contact_phone=body.get("contact_phone"),
            permissions=body.get("permissions", {
                "view_all_classes": True,
                "export_reports": True,
                "manage_teachers": False,
            }),
        )
        db.add(admin)
        await db.flush()
        return SchoolAdminOut.model_validate(admin)

    @staticmethod
    async def list_admins(db: AsyncSession) -> list[SchoolAdminOut]:
        """获取所有学校管理员"""
        result = await db.execute(
            select(SchoolAdmin).where(SchoolAdmin.is_active == 1)
            .order_by(SchoolAdmin.created_at.desc())
        )
        return [SchoolAdminOut.model_validate(a) for a in result.scalars().all()]

    @staticmethod
    async def get_school_dashboard(
        db: AsyncSession, admin_id: int,
    ) -> SchoolDashboardOut:
        """获取学校级数据看板"""
        admin = await db.execute(
            select(SchoolAdmin).where(
                SchoolAdmin.user_id == admin_id, SchoolAdmin.is_active == 1
            )
        )
        admin_row = admin.scalar_one_or_none()
        if not admin_row:
            raise ValueError("无权访问学校数据")

        # 统计所有班级
        classes = await db.execute(
            select(Class, func.count(ClassStudent.id).label("student_cnt"))
            .outerjoin(ClassStudent, ClassStudent.class_id == Class.id)
            .group_by(Class.id)
        )
        class_rows = classes.all()

        class_stats = []
        total_students = 0
        total_teachers_set = set()
        for cls, student_cnt in class_rows:
            total_students += student_cnt or 0

            # 获取班级教师数
            teachers = await db.execute(
                select(ClassTeacher.teacher_id).where(
                    ClassTeacher.class_id == cls.id,
                    ClassTeacher.role == "teacher",
                )
            )
            for t in teachers.all():
                total_teachers_set.add(t[0])

            class_stats.append({
                "class_id": cls.id,
                "class_name": cls.name,
                "student_count": student_cnt or 0,
                "stage": cls.stage,
            })

        return SchoolDashboardOut(
            school_name=admin_row.school_name,
            total_classes=len(class_rows),
            total_students=total_students,
            total_teachers=len(total_teachers_set),
            total_exams=0,
            class_stats=class_stats,
        )

    @staticmethod
    async def toggle_admin(
        db: AsyncSession, user_id: int, operator_id: int,
    ) -> bool:
        """启用/禁用学校管理员"""
        admin = await db.execute(
            select(SchoolAdmin).where(SchoolAdmin.user_id == user_id)
        )
        admin_row = admin.scalar_one_or_none()
        if not admin_row:
            return False
        admin_row.is_active = 1 - admin_row.is_active
        await db.flush()
        return True
