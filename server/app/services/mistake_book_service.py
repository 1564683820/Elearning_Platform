"""
错题本 Service — 提供错题本三类数据聚合服务
"""
from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz import WrongQuestion, QuestionBank, ReadingMaterial
from app.models.exam_models import ExamSubmission, TeacherExam
from app.models.mistake_book import MistakeSummaryReport


class MistakeBookService:
    """错题本服务"""

    @staticmethod
    async def get_word_training_mistakes(
        db: AsyncSession, user_id: int, page: int = 1, page_size: int = 50
    ) -> dict:
        """获取单词训练和阅读训练错题"""
        stmt = select(
            WrongQuestion, QuestionBank.content, QuestionBank.type,
            QuestionBank.stage, QuestionBank.reading_id, ReadingMaterial
        ).join(
            QuestionBank, WrongQuestion.question_id == QuestionBank.id,
            isouter=True,
        ).outerjoin(
            ReadingMaterial, QuestionBank.reading_id == ReadingMaterial.id,
        ).where(
            WrongQuestion.user_id == user_id,
            WrongQuestion.question_type.in_([1, 6]),  # 1=单词, 6=阅读
            WrongQuestion.mastered == 0,               # 未掌握
        ).order_by(WrongQuestion.last_wrong_at.desc())

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        result = await db.execute(stmt)
        rows = result.all()

        items = []
        for row in rows:
            wq = row[0]
            qb_content = row[1] if row[1] else {}
            qb_type = row[2] if len(row) > 2 else 1
            reading_material = row[5] if len(row) > 5 else None

            if isinstance(qb_content, str):
                try:
                    import json
                    qb_content = json.loads(qb_content)
                except Exception:
                    qb_content = {}

            stem = qb_content.get("stem", qb_content.get("question", ""))
            correct = qb_content.get("correct", qb_content.get("answer", ""))
            options = qb_content.get("options", [])
            explanation = qb_content.get("explanation", qb_content.get("analysis", ""))

            item = {
                "id": wq.id,
                "question_id": wq.question_id,
                "stem": stem,
                "options": options,
                "correct_answer": correct,
                "explanation": explanation,
                "wrong_count": wq.wrong_count,
                "last_wrong_at": str(wq.last_wrong_at)[:10] if wq.last_wrong_at else "",
                "category": wq.category or "",
                "knowledge_point": wq.knowledge_point or "",
                "type": qb_type,
            }

            # 阅读错题：附带文章标题、原文、翻译
            if qb_type == 6 and reading_material:
                item["article_title"] = reading_material.title or ""
                item["article_content"] = reading_material.content or ""
                item["article_translation"] = reading_material.content_cn or ""

            items.append(item)

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    async def get_exam_mistakes(
        db: AsyncSession, user_id: int, page: int = 1, page_size: int = 20
    ) -> dict:
        """获取试卷错题：从考试提交记录中提取错题"""
        # 获取用户所有已批改的考试提交
        # 同时查询 ai_done、teacher_reviewed 和 pending（含写作/翻译等需复核的题型）
        # ai_grade_detail 在提交时即已写入，pending 状态的提交也可以提取错题
        sub_stmt = select(ExamSubmission).where(
            ExamSubmission.student_id == user_id,
            ExamSubmission.grading_status.in_(["ai_done", "teacher_reviewed", "pending"]),
        ).order_by(ExamSubmission.submitted_at.desc()).limit(50)

        sub_result = await db.execute(sub_stmt)
        submissions = sub_result.scalars().all()

        if not submissions:
            return {"items": [], "total": 0}

        exam_ids = list(set(s.exam_id for s in submissions))
        exam_stmt = select(TeacherExam).where(TeacherExam.id.in_(exam_ids))
        exam_result = await db.execute(exam_stmt)
        exam_map = {e.id: e for e in exam_result.scalars().all()}

        items = []
        for sub in submissions:
            exam = exam_map.get(sub.exam_id)
            if not exam:
                continue

            grade_detail = sub.ai_grade_detail or []
            wrong_questions = []
            for q in grade_detail:
                if isinstance(q, dict):
                    is_correct = q.get("is_correct", False)
                    score = q.get("score", 0)
                    max_score = q.get("max_score", 1)
                    if not is_correct and (max_score <= 0 or score < max_score * 0.7):
                        wrong_questions.append(q)

            if wrong_questions:
                items.append({
                    "exam_id": exam.id,
                    "exam_title": exam.title,
                    "score": sub.score,
                    "max_score": sub.max_score,
                    "submitted_at": str(sub.submitted_at)[:10] if sub.submitted_at else "",
                    "wrong_count": len(wrong_questions),
                    "wrong_questions": [{
                        "index": q.get("index", 0),
                        "type": q.get("type", ""),
                        "stem": q.get("stem", ""),
                        "user_answer": q.get("user_answer", ""),
                        "correct_answer": q.get("correct_answer", ""),
                        "score": q.get("score", 0),
                        "max_score": q.get("max_score", 0),
                        "ai_comment": q.get("ai_comment", ""),
                    } for q in wrong_questions[:20]],
                })

        # 分页
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = items[start:end] if start < total else []

        return {"items": page_items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    async def get_summary_reports(
        db: AsyncSession, user_id: int, page: int = 1, page_size: int = 20
    ) -> dict:
        """获取小e总结报告列表"""
        stmt = select(MistakeSummaryReport).where(
            MistakeSummaryReport.user_id == user_id
        ).order_by(MistakeSummaryReport.created_at.desc())

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        result = await db.execute(stmt)
        reports = result.scalars().all()

        items = [{
            "id": r.id,
            "title": r.title,
            "content": r.content,  # Markdown 全文
            "exam_name": r.exam_name or "",
            "days": r.days,
            "created_at": str(r.created_at)[:16] if r.created_at else "",
        } for r in reports]

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    async def save_summary_report(
        db: AsyncSession, user_id: int, title: str,
        content: str, exam_name: str = "", days: int = 0
    ) -> dict:
        """保存小e总结报告"""
        report = MistakeSummaryReport(
            user_id=user_id,
            title=title,
            content=content,
            exam_name=exam_name,
            days=days,
        )
        db.add(report)
        await db.flush()
        return {"id": report.id, "title": title, "created_at": str(report.created_at)[:16]}

    @staticmethod
    async def batch_delete_word_mistakes(
        db: AsyncSession, user_id: int, ids: list[int]
    ) -> int:
        """批量删除单词训练错题"""
        stmt = select(WrongQuestion).where(
            WrongQuestion.id.in_(ids),
            WrongQuestion.user_id == user_id,
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        for row in rows:
            await db.delete(row)
        await db.flush()
        return len(rows)

    @staticmethod
    async def batch_delete_summary_reports(
        db: AsyncSession, user_id: int, ids: list[int]
    ) -> int:
        """批量删除小e总结报告"""
        stmt = select(MistakeSummaryReport).where(
            MistakeSummaryReport.id.in_(ids),
            MistakeSummaryReport.user_id == user_id,
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        for row in rows:
            await db.delete(row)
        await db.flush()
        return len(rows)

    @staticmethod
    async def get_report_detail(
        db: AsyncSession, user_id: int, report_id: int
    ) -> dict | None:
        """获取单条报告详情"""
        result = await db.execute(
            select(MistakeSummaryReport).where(
                MistakeSummaryReport.id == report_id,
                MistakeSummaryReport.user_id == user_id,
            )
        )
        r = result.scalar_one_or_none()
        if not r:
            return None
        return {
            "id": r.id,
            "title": r.title,
            "content": r.content,
            "created_at": str(r.created_at)[:16] if r.created_at else "",
            "exam_name": r.exam_name or "",
            "days": r.days,
        }
