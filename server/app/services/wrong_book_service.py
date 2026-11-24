# 错题本服务
# 错题入库、统计查询、RAG索引触发
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.scan_models import WrongQuestionBook
from app.models.exam_models import TeacherExam, ExamSubmission
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)


class WrongBookService:
    """错题本服务：错题入库、查询、统计、RAG索引"""

    @staticmethod
    async def save_from_submission(
        db: AsyncSession,
        submission: ExamSubmission,
    ) -> int:
        """从提交记录提取错题写入 wrong_question_book

        根据 ai_grade_detail 判断每道题是否正确，
        不正确的题目逐题入库（去重检查 submission_id + question_index）。

        返回: 当前提交仍有效的错题数量（含已有记录）
        """
        exam = await db.get(TeacherExam, submission.exam_id)
        if not exam:
            logger.warning(f"save_from_submission: 试卷 {submission.exam_id} 不存在")
            return 0

        questions = exam.questions or []
        grade_detail = submission.ai_grade_detail or []

        saved_count = 0
        for grade_item in grade_detail:
            q_idx = grade_item.get("index", 0)  # 0-based index
            q_number = grade_item.get("question_number", q_idx + 1)
            is_correct = grade_item.get("is_correct", True)
            q_score = grade_item.get("score", 0)
            q_max = grade_item.get("max_score", 0)

            # 获取题干和知识点
            q_data = questions[q_idx] if q_idx < len(questions) else {}
            sub_questions = q_data.get("sub_questions") or q_data.get("questions") or []
            sub_index = grade_item.get("sub_index")
            if isinstance(sub_index, int) and 0 <= sub_index < len(sub_questions):
                q_data = {**q_data, **sub_questions[sub_index]}
            stem = q_data.get("stem", q_data.get("question", ""))
            knowledge = q_data.get("knowledge_point", "")

            # 检查是否已存在（唯一约束）
            stmt = select(WrongQuestionBook).where(
                WrongQuestionBook.submission_id == submission.id,
                WrongQuestionBook.question_index == q_number,
            )
            existing = (await db.execute(stmt)).scalar_one_or_none()
            # 重批后变正确的题必须从当前错题集合移除。
            if is_correct and q_max > 0 and q_score >= q_max * 0.7:
                if existing:
                    await db.delete(existing)
                continue
            saved_count += 1
            if existing:
                # 更新已有的错题记录（可能有教师复核后的变化）
                existing.score = q_score
                existing.max_score = q_max
                existing.student_answer = grade_item.get("user_answer", existing.student_answer)
                existing.correct_answer = grade_item.get("correct_answer", existing.correct_answer)
                existing.ai_comment = grade_item.get("ai_comment", existing.ai_comment)
                existing.rag_indexed = 0
                continue

            wrong_q = WrongQuestionBook(
                student_id=submission.student_id,
                class_id=exam.class_id,
                exam_id=exam.id,
                submission_id=submission.id,
                question_index=q_number,
                question_type=q_data.get("type", ""),
                question_stem=stem,
                correct_answer=grade_item.get("correct_answer", ""),
                student_answer=grade_item.get("user_answer", ""),
                knowledge_point=knowledge,
                score=q_score,
                max_score=q_max,
                ai_comment=grade_item.get("ai_comment", ""),
                rag_indexed=0,
            )
            db.add(wrong_q)

        # 更新提交记录的错题计数
        submission.wrong_count = saved_count
        try:
            flag_modified(submission, "wrong_count")
        except Exception:
            pass

        await db.flush()
        logger.info(f"错题入库: submission_id={submission.id}, exam_id={exam.id}, 错题数={saved_count}")
        return saved_count

    @staticmethod
    async def remove_from_submission(db: AsyncSession, submission_id: int) -> None:
        await db.execute(delete(WrongQuestionBook).where(WrongQuestionBook.submission_id == submission_id))

    @staticmethod
    async def index_to_rag(
        db: AsyncSession,
        submission_id: int,
    ) -> int:
        """将错题异步索引到RAG向量库

        针对 submission_id 下所有未索引的错题，逐个调用 RAGService 索引。

        返回: 成功索引的数量
        """
        stmt = select(WrongQuestionBook).where(
            WrongQuestionBook.submission_id == submission_id,
            WrongQuestionBook.rag_indexed == 0,
        )
        result = await db.execute(stmt)
        wrong_qs = result.scalars().all()

        indexed_count = 0
        for wq in wrong_qs:
            try:
                # 构建完整错题内容：包含题干、学生答案、正确答案、AI评语
                full_content_parts = []
                if wq.question_stem:
                    full_content_parts.append(f"题干：{wq.question_stem}")
                if wq.student_answer:
                    full_content_parts.append(f"学生答案：{wq.student_answer}")
                if wq.correct_answer:
                    full_content_parts.append(f"正确答案：{wq.correct_answer}")
                if wq.error_category:
                    full_content_parts.append(f"错误分类：{wq.error_category}")
                if wq.ai_comment:
                    full_content_parts.append(f"AI评语：{wq.ai_comment}")
                if wq.score is not None and wq.max_score:
                    full_content_parts.append(f"得分：{wq.score}/{wq.max_score}")
                full_content = "\n".join(full_content_parts) if full_content_parts else (wq.question_stem or "")

                success = await RAGService.index_wrong_question_for_rag(
                    db=db,
                    user_id=wq.student_id,
                    question_id=wq.id,
                    question_content=full_content,
                    question_type=1,
                    category="exam_scan",
                    knowledge_point=wq.knowledge_point,
                    class_id=wq.class_id,
                )
                if success:
                    wq.rag_indexed = 1
                    wq.rag_chunk_id = f"wq_{wq.id}"
                    indexed_count += 1
            except Exception as e:
                logger.error(f"RAG索引失败: wq_id={wq.id}, error={e}")

        if indexed_count > 0:
            await db.flush()
            logger.info(f"RAG索引完成: submission_id={submission_id}, 索引数={indexed_count}")

        return indexed_count

    @staticmethod
    async def get_student_wrong_book(
        db: AsyncSession,
        student_id: int,
        page: int = 1,
        page_size: int = 20,
        knowledge_point: Optional[str] = None,
        class_id: Optional[int] = None,
    ) -> dict:
        """查询个人错题本（分页）"""
        query = select(WrongQuestionBook).where(
            WrongQuestionBook.student_id == student_id,
        )

        if knowledge_point:
            query = query.where(WrongQuestionBook.knowledge_point == knowledge_point)
        if class_id:
            query = query.where(WrongQuestionBook.class_id == class_id)

        # 总条数
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        # 分页
        query = query.order_by(WrongQuestionBook.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        items = result.scalars().all()

        # 获取试卷标题
        exam_ids = list(set(w.exam_id for w in items))
        exam_titles = {}
        if exam_ids:
            exam_stmt = select(TeacherExam.id, TeacherExam.title).where(
                TeacherExam.id.in_(exam_ids)
            )
            exam_result = await db.execute(exam_stmt)
            exam_titles = {row[0]: row[1] for row in exam_result}

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": w.id,
                    "exam_id": w.exam_id,
                    "exam_title": exam_titles.get(w.exam_id, ""),
                    "question_index": w.question_index,
                    "question_type": w.question_type,
                    "question_stem": w.question_stem,
                    "correct_answer": w.correct_answer,
                    "student_answer": w.student_answer,
                    "knowledge_point": w.knowledge_point,
                    "score": w.score,
                    "max_score": w.max_score,
                    "ai_comment": w.ai_comment,
                    "created_at": w.created_at.isoformat() if w.created_at else None,
                }
                for w in items
            ],
        }

    @staticmethod
    async def get_wrong_book_stats(
        db: AsyncSession,
        student_id: int,
        class_id: Optional[int] = None,
    ) -> dict:
        """按知识点聚合错题统计"""
        query = select(
            WrongQuestionBook.knowledge_point,
            func.count().label("count"),
        ).where(
            WrongQuestionBook.student_id == student_id,
            WrongQuestionBook.knowledge_point != "",
        )
        if class_id:
            query = query.where(WrongQuestionBook.class_id == class_id)

        query = query.group_by(WrongQuestionBook.knowledge_point)
        query = query.order_by(func.count().desc())

        result = await db.execute(query)
        rows = result.all()

        total_wrong = sum(row[1] for row in rows)
        by_knowledge = [
            {
                "knowledge_point": row[0],
                "count": row[1],
                "accuracy_rate": 0.0,  # 由前端或后续调用计算
            }
            for row in rows
        ]
        weak_points = [row[0] for row in rows[:5]] if rows else []

        return {
            "total_wrong": total_wrong,
            "by_knowledge": by_knowledge,
            "weak_points": weak_points,
        }

    @staticmethod
    async def validate_wrong_questions_exist(
        db: AsyncSession,
        exam_id: int,
    ) -> bool:
        """检查试卷是否有错题记录"""
        stmt = select(func.count()).where(
            WrongQuestionBook.exam_id == exam_id,
        )
        count = (await db.execute(stmt)).scalar() or 0
        return count > 0
