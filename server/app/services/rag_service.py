from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from app.services.ai_service import AIService
from app.services.embedding_service import EmbeddingService
from app.services.document_service import get_source_type_for_category
from app.services.document_progress import update_embed_progress
from app.services.parent_chunk_store import auto_merge
from app.services.chunk_manager import ChunkInfo
from app.services.upload_job_manager import update_job_step
from datetime import datetime, timedelta
from typing import Optional
import json
import logging

logger = logging.getLogger(__name__)


class RAGService:
    """RAG 检索增强生成：混合检索 + Auto-merging + 多维度 RAG"""

    @staticmethod
    async def answer_question(
        db: AsyncSession,
        query: str,
        user_id: int | None = None,
        stage: str = "",
        use_hybrid: bool = True,
    ) -> dict:
        """RAG 问答：混合检索 → Auto-merge → Prompt → LLM 生成

        参数:
            use_hybrid: True=混合检索(稠密+稀疏), False=纯稠密检索
        """
        coll = EmbeddingService.TEACHER_DOCUMENTS
        if use_hybrid:
            search_results = await EmbeddingService.hybrid_search(
                db, query, coll, top_k=5,
                user_id=user_id or 0, stage=stage,
            )
        else:
            search_results = await EmbeddingService.search(
                db, query, coll, top_k=5,
                user_id=user_id or 0, stage=stage,
            )

        # Auto-merge：将叶子块按父块合并
        try:
            search_results = await auto_merge(db, search_results)
        except Exception:
            pass  # auto-merge 失败不影响主流程

        context_parts = []
        sources = []
        for i, result in enumerate(search_results):
            doc_label = result.get("doc_title") or result.get("source_type", "unknown")
            context_parts.append(f"[{i+1}] [{doc_label}] {result['content']}")
            sources.append({
                "type": result["source_type"],
                "id": result["source_id"],
                "title": result.get("doc_title", result.get("source_type", "unknown")),
                "score": result["score"],
                "merged_level": result.get("merged_level", 3),
            })

        context = "\n\n".join(context_parts) if context_parts else "暂无相关参考资料。"

        system_prompt = (
            "你是一个专业的英语学习助手。请根据以下参考资料回答用户的问题。\n"
            "如果参考资料不足以回答问题，请根据你的知识补充，并标注'以下内容非参考来源'。\n"
            "回答要简洁、准确、有条理。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"参考资料：\n{context}\n\n用户问题：{query}"},
        ]

        answer = await AIService.chat_completion(db, messages, user_id)

        return {
            "answer": answer,
            "sources": sources,
            "context_used": len(search_results),
        }

    @staticmethod
    async def index_document_chunks(
        db: AsyncSession,
        chunks: list[ChunkInfo],
        source_type: str,
        source_id: int,
        user_id: int = 0,
        stage: str = "",
        doc_category: str = "other",
        doc_title: str = "",      # 文档原始文件名，写入 Milvus 便于标量检索
        doc_tags: str = "",       # 文档自定义标签，写入 Milvus 便于过滤
        doc_id: int | None = None,
        job_id: str | None = None,
        class_id: int = 0,
    ) -> int:
        """批量将三级分块向量化写入 Milvus（稠密 + 稀疏双向量）

        参数:
            chunks: ChunkInfo 列表（应有且仅有 Level 3 叶子块）
            job_id: 上传 job_id，用于进度上报
        """
        if not source_type.startswith("doc_"):
            source_type = get_source_type_for_category(doc_category)

        total = len(chunks)
        # 按 64 条一批分片，每批一次 HTTP 请求
        batch_size = 64
        success_count = 0

        for batch_start in range(0, total, batch_size):
            batch = chunks[batch_start:batch_start + batch_size]
            batch_dicts = [
                {
                    "content": c.content,
                    "source_type": source_type,
                    "source_id": source_id,
                    "level": c.level,
                    "chunk_id": c.chunk_id,
                    "parent_chunk_id": c.parent_chunk_id or "",
                    "root_chunk_id": c.root_chunk_id or "",
                    "chunk_order": c.seq,
                    "section_title": getattr(c, "section_title", "") or "",
                }
                for c in batch
            ]
            # 构建 teacher_documents 额外字段
            doc_info = {
                "doc_category": doc_category,
                "doc_title": doc_title,
                "doc_tags": doc_tags,
            }
            if class_id:
                doc_info["class_id"] = class_id
            for d in batch_dicts:
                d.update(doc_info)
            batch_count = await EmbeddingService.index_chunks_batch(
                db, EmbeddingService.TEACHER_DOCUMENTS, batch_dicts,
                user_id=user_id, stage=stage,
            )
            success_count += batch_count

            # 进度上报（每批完成后）
            done = min(batch_start + batch_size, total)
            pct = int(done / total * 100) if total > 0 else 0
            msg = f"正在入库 {done}/{total} 块"
            if doc_id is not None:
                await update_embed_progress(doc_id, done, total)
            if job_id is not None:
                await update_job_step(job_id, "embed", pct, "running", msg)

        return success_count

    @staticmethod
    async def index_wrong_question_for_rag(
        db: AsyncSession,
        user_id: int,
        question_id: int,
        question_content: str,
        question_type: int,
        category: str = "",
        knowledge_point: str = "",
        stage: str = "",
        class_id: int = 0,
    ) -> bool:
        """将错题文本向量化存入 Milvus（含稀疏向量）"""
        if not question_content:
            return False

        source_type = f"wrong_question_{category}" if category else "wrong_question"
        content_text = f"[{knowledge_point}] {question_content}" if knowledge_point else question_content

        extra = dict(
            source_type=source_type,
            source_id=question_id,
            user_id=user_id,
            stage=stage,
            level=3,
            chunk_id=f"wq_{question_id}",
            category=category,
            knowledge_point=knowledge_point,
            question_type=question_type,
        )
        if class_id:
            extra["class_id"] = class_id

        result = await EmbeddingService.index_chunk(
            db, EmbeddingService.STUDENT_ERRORS,
            content_text,
            **extra,
        )
        return result

    @staticmethod
    async def search_student_errors(
        db: AsyncSession,
        query: str,
        user_id: int = 0,
        category: str = "",
        stage: str = "",
        top_k: int = 10,
        use_hybrid: bool = False,
        class_id: int = 0,
    ) -> list[dict]:
        """检索学生错题数据（支持混合检索）"""
        extra_filters = ["source_type like 'wrong_question%'"]
        if user_id:
            extra_filters.append(f"user_id == {user_id}")
        if category:
            extra_filters.append(f'source_type == "wrong_question_{category}"')

        extra_filter_str = " and ".join(extra_filters)

        coll = EmbeddingService.STUDENT_ERRORS
        if use_hybrid:
            return await EmbeddingService.hybrid_search(
                db, query, coll, top_k=top_k,
                user_id=user_id if user_id else 0, stage=stage,
                extra_filter=extra_filter_str, class_id=class_id,
            )
        return await EmbeddingService.search(
            db, query, coll, top_k=top_k,
            user_id=user_id if user_id else 0, stage=stage,
            extra_filter=extra_filter_str, class_id=class_id,
        )

    # ---------- 以下方法保持不变（班级分析、统计数据、弱项分析）----------

    @staticmethod
    async def get_class_error_analysis(
        db: AsyncSession,
        class_id: int,
        days: int = 7,
    ) -> dict:
        """获取班级错题统计分析（按知识点维度）"""
        from app.models.quiz import WrongQuestion
        from app.models.class_models import ClassStudent

        student_ids_stmt = select(ClassStudent.student_id).where(ClassStudent.class_id == class_id)
        student_ids_result = await db.execute(student_ids_stmt)
        student_ids = [row[0] for row in student_ids_result.all()]

        if not student_ids:
            return {"student_count": 0, "total_mistakes": 0, "category_distribution": []}

        since_date = datetime.now() - timedelta(days=days)
        stmt = select(
            WrongQuestion.category,
            func.count(WrongQuestion.id).label("count"),
        ).where(
            WrongQuestion.user_id.in_(student_ids),
            WrongQuestion.last_wrong_at >= since_date,
        ).group_by(WrongQuestion.category)

        result = await db.execute(stmt)
        distribution = [
            {"category": row[0] or "uncategorized", "count": row[1]}
            for row in result.all()
        ]

        total_stmt = select(func.count()).select_from(WrongQuestion).where(
            WrongQuestion.user_id.in_(student_ids),
            WrongQuestion.last_wrong_at >= since_date,
        )
        total = (await db.execute(total_stmt)).scalar() or 0

        return {
            "student_count": len(student_ids),
            "total_mistakes": total,
            "category_distribution": distribution,
            "days": days,
        }

    @staticmethod
    async def class_rag_query(
        db: AsyncSession,
        class_id: int,
        query: str,
        days: int = 30,
        knowledge_point: str = "",
        top_k: int = 10,
    ) -> dict:
        """班级级 RAG 查询"""
        from app.models.quiz import WrongQuestion
        from app.models.class_models import ClassStudent
        from app.models.stats import UserDailyStat

        student_ids_stmt = select(ClassStudent.student_id).where(ClassStudent.class_id == class_id)
        student_ids_result = await db.execute(student_ids_stmt)
        student_ids = [row[0] for row in student_ids_result.all()]

        if not student_ids:
            return {"student_count": 0, "results": [], "context_summary": "该班级暂无学生数据"}

        since_date = None
        if days > 0:
            since_date = datetime.now() - timedelta(days=days)

        # Milvus 语义检索（按班级过滤）
        search_results = []
        try:
            search_results = await EmbeddingService.search(
                db, query, EmbeddingService.STUDENT_ERRORS, top_k=top_k,
                extra_filter="source_type like 'wrong_question%'",
                class_id=class_id,
            )
        except Exception:
            pass

        # 数据库统计分析
        wq_stmt = select(
            WrongQuestion.knowledge_point,
            func.count().label("cnt"),
        ).where(
            WrongQuestion.user_id.in_(student_ids),
            WrongQuestion.knowledge_point.isnot(None),
        )
        if since_date:
            wq_stmt = wq_stmt.where(WrongQuestion.last_wrong_at >= since_date)
        if knowledge_point:
            wq_stmt = wq_stmt.where(WrongQuestion.knowledge_point == knowledge_point)
        wq_stmt = wq_stmt.group_by(WrongQuestion.knowledge_point).order_by(func.count().desc()).limit(10)

        wq_result = await db.execute(wq_stmt)
        top_mistakes = [{"knowledge_point": row[0], "count": row[1]} for row in wq_result.all()]

        total_quiz = await db.execute(
            select(func.count()).where(UserDailyStat.user_id.in_(student_ids))
        )
        total_correct = await db.execute(
            select(func.sum(UserDailyStat.quiz_correct)).where(UserDailyStat.user_id.in_(student_ids))
        )
        total_q = total_quiz.scalar() or 0
        total_c = total_correct.scalar() or 0

        context_summary = (
            f"班级共 {len(student_ids)} 名学生。"
            f"总做题数 {total_q}，总正确率 {round(total_c / total_q * 100, 1) if total_q > 0 else 0}%。"
        )
        if top_mistakes:
            context_summary += f" 高频错题知识点：{'、'.join([m['knowledge_point'] for m in top_mistakes[:5]])}。"

        return {
            "student_count": len(student_ids),
            "semantic_results": search_results,
            "top_mistakes": top_mistakes,
            "context_summary": context_summary,
        }

    @staticmethod
    async def generate_nl_query_answer(
        db: AsyncSession,
        class_id: int,
        question: str,
        teacher_id: int,
    ) -> str:
        """AI 自然语言查询"""
        from app.models.class_models import Class

        cls = await db.get(Class, class_id)
        if not cls:
            return "班级不存在"

        rag_data = await RAGService.class_rag_query(db, class_id, question, days=30, top_k=5)

        student_count = rag_data.get("student_count", 0)
        top_mistakes = rag_data.get("top_mistakes", [])
        context_summary = rag_data.get("context_summary", "")

        system_prompt = (
            "你是一个专业的英语教师数据分析助手。你的职责是根据班级学习数据回答教师的问题。\n\n"
            "回答要求：\n"
            "1. 基于提供的班级数据，回答要准确、具体\n"
            "2. 回答包含具体数字和百分比，不使用模糊表述\n"
            "3. 如果数据不足以回答，请明确说明\n"
            "4. 回答要简洁易懂，适合教师快速了解情况\n"
            "5. 可以给出教学建议\n\n"
            "当前班级信息：\n"
            f"班级名称：{cls.name}\n"
            f"学生人数：{student_count}\n"
            f"{context_summary}\n"
        )

        if top_mistakes:
            mistakes_str = "、".join(
                [f"{m['knowledge_point']}({m['count']}次)" for m in top_mistakes[:5]]
            )
            system_prompt += f"\n高频错题知识点TOP5：{mistakes_str}\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]

        answer = await AIService.chat_completion(db, messages, teacher_id)
        return answer.strip()

    @staticmethod
    async def generate_nl_query_answer_stream(
        db: AsyncSession,
        class_id: int,
        question: str,
        teacher_id: int,
    ):
        """AI 自然语言查询 — SSE 流式版本，逐字符产生 chunk 事件"""
        from app.models.class_models import Class

        cls = await db.get(Class, class_id)
        if not cls:
            yield f"event: chunk\ndata: {json.dumps({'content': '班级不存在'}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'content': '班级不存在'}, ensure_ascii=False)}\n\n"
            return

        yield f"event: status\ndata: {json.dumps({'message': '正在查询班级数据...'}, ensure_ascii=False)}\n\n"
        rag_data = await RAGService.class_rag_query(db, class_id, question, days=30, top_k=5)

        student_count = rag_data.get("student_count", 0)
        top_mistakes = rag_data.get("top_mistakes", [])
        context_summary = rag_data.get("context_summary", "")

        system_prompt = (
            "你是一个专业的英语教师数据分析助手。你的职责是根据班级学习数据回答教师的问题。\n\n"
            "回答要求：\n"
            "1. 基于提供的班级数据，回答要准确、具体\n"
            "2. 回答包含具体数字和百分比，不使用模糊表述\n"
            "3. 如果数据不足以回答，请明确说明\n"
            "4. 回答要简洁易懂，适合教师快速了解情况\n"
            "5. 可以给出教学建议\n"
            "6. 使用 Markdown 格式排版，适当使用标题、列表、加粗等语法让回答更清晰易读\n\n"
            "当前班级信息：\n"
            f"班级名称：{cls.name}\n"
            f"学生人数：{student_count}\n"
            f"{context_summary}\n"
        )

        if top_mistakes:
            mistakes_str = "、".join(
                [f"{m['knowledge_point']}({m['count']}次)" for m in top_mistakes[:5]]
            )
            system_prompt += f"\n高频错题知识点TOP5：{mistakes_str}\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]

        yield f"event: status\ndata: {json.dumps({'message': '小e正在生成回答...'}, ensure_ascii=False)}\n\n"
        full_answer = ""
        try:
            stream_gen = await AIService.chat_completion(
                db, messages, teacher_id, stream=True, max_tokens=4096,
            )
            async for chunk in stream_gen:
                full_answer += chunk
                yield f"event: chunk\ndata: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"AI 流式查询失败: {e}")
            err_msg = "抱歉，查询时出现错误，请稍后再试。"
            full_answer = err_msg
            yield f"event: chunk\ndata: {json.dumps({'content': err_msg}, ensure_ascii=False)}\n\n"

        yield f"event: done\ndata: {json.dumps({'content': full_answer.strip()}, ensure_ascii=False)}\n\n"

    @staticmethod
    async def generate_error_summary_report(
        db: AsyncSession,
        user_id: int,
        exam_name: str | None = None,
        days: int | None = None,
        include_vocab: bool = True,
        user_query: str = "",
    ) -> str:
        """智能生成错题总结报告（含答案解析 + 学习建议 + 精美排版）

        Args:
            db: 数据库会话
            user_id: 用户ID
            exam_name: 指定考试名称（None=查询所有）
            days: 时间范围天数（None=不限）
            include_vocab: 是否包含单词训练错题
            user_query: 用户原始问题
        Returns:
            Markdown 格式的错题报告
        """
        from datetime import datetime, timedelta
        from app.models.quiz import WrongQuestion, QuestionBank
        from app.models.exam_models import ExamSubmission, TeacherExam

        # ========== 1. 查询训练错题 ==========
        wq_stmt = select(
            WrongQuestion, QuestionBank.content, QuestionBank.type,
            QuestionBank.stage,
        ).join(
            QuestionBank, WrongQuestion.question_id == QuestionBank.id,
            isouter=True,
        ).where(
            WrongQuestion.user_id == user_id,
        )

        if days is not None:
            since = datetime.now() - timedelta(days=days)
            wq_stmt = wq_stmt.where(WrongQuestion.last_wrong_at >= since)

        if not include_vocab:
            wq_stmt = wq_stmt.where(WrongQuestion.question_type != 1)

        wq_stmt = wq_stmt.order_by(WrongQuestion.last_wrong_at.desc()).limit(30)
        wq_result = await db.execute(wq_stmt)
        training_errors = wq_result.all()

        # ========== 2. 查询考试错题 ==========
        exam_errors = []
        target_exam_id = None

        if exam_name:
            # 按考试名称查找
            exam_stmt = select(TeacherExam).where(
                TeacherExam.title.like(f"%{exam_name}%"),
            ).order_by(TeacherExam.created_at.desc()).limit(5)
            exam_result = await db.execute(exam_stmt)
            exams = exam_result.scalars().all()
        else:
            # 获取用户最近的所有考试提交
            exam_stmt = select(TeacherExam).order_by(TeacherExam.created_at.desc()).limit(20)
            exam_result = await db.execute(exam_stmt)
            exams = exam_result.scalars().all()

        if exams:
            exam_ids = [e.id for e in exams]
            sub_stmt = select(ExamSubmission).where(
                ExamSubmission.student_id == user_id,
                ExamSubmission.exam_id.in_(exam_ids),
                ExamSubmission.grading_status.in_(["ai_done", "teacher_reviewed", "pending"]),
            )
            if days is not None:
                since = datetime.now() - timedelta(days=days)
                sub_stmt = sub_stmt.where(ExamSubmission.submitted_at >= since)
            sub_result = await db.execute(sub_stmt)
            submissions = sub_result.scalars().all()

            exam_map = {e.id: e for e in exams}
            for sub in submissions:
                exam = exam_map.get(sub.exam_id)
                if not exam:
                    continue
                if exam_name and exam_name not in exam.title:
                    continue

                grade_detail = sub.ai_grade_detail or []
                wrong_questions = []
                for q in grade_detail:
                    if isinstance(q, dict):
                        is_correct = q.get("is_correct", False)
                        if not is_correct and not q.get("score", 0) >= q.get("max_score", 1) * 0.7:
                            wrong_questions.append(q)

                if wrong_questions:
                    exam_errors.append({
                        "exam_title": exam.title,
                        "exam_id": exam.id,
                        "score": sub.score,
                        "max_score": sub.max_score,
                        "submitted_at": str(sub.submitted_at)[:10] if sub.submitted_at else "",
                        "wrong_questions": wrong_questions[:10],
                    })

        # ========== 3. 构建数据上下文 ==========

        # 训练错题汇总
        training_summary = []
        category_stats = {}
        for row in training_errors:
            wq = row[0]
            qb_content = row[1] if row[1] else {}
            if isinstance(qb_content, str):
                try:
                    qb_content = json.loads(qb_content)
                except (json.JSONDecodeError, TypeError):
                    qb_content = {}

            stem = qb_content.get("stem", qb_content.get("question", ""))
            correct = qb_content.get("correct", qb_content.get("answer", ""))
            explanation = qb_content.get("explanation", qb_content.get("analysis", ""))
            options = qb_content.get("options", [])

            training_summary.append({
                "category": wq.category or "uncategorized",
                "knowledge_point": wq.knowledge_point or "",
                "stem": stem,
                "correct_answer": correct,
                "options": options,
                "explanation": explanation,
                "wrong_count": wq.wrong_count,
                "question_type": wq.question_type,
                "last_wrong_at": str(wq.last_wrong_at)[:10] if wq.last_wrong_at else "",
            })

            cat = wq.category or "其他"
            category_stats[cat] = category_stats.get(cat, 0) + 1

        # 按分类排序
        category_stats = dict(sorted(category_stats.items(), key=lambda x: x[1], reverse=True))

        # ========== 4. 调用 LLM 生成报告 ==========

        # 构建结构化上下文
        context_parts = []

        if training_summary:
            context_parts.append("## 训练错题")
            for i, err in enumerate(training_summary, 1):
                opts_str = ""
                if err["options"]:
                    letters = ["A", "B", "C", "D", "E", "F"]
                    opts_str = "\n".join(
                        f"  {letters[j]}. {opt}" for j, opt in enumerate(err["options"])
                    )
                context_parts.append(
                    f"### {i}. [{err['category'].upper()}] {err['knowledge_point'] or '通用'}\n"
                    f"- **题目**：{err['stem']}\n"
                    f"{'- 选项：' + chr(10) + opts_str if opts_str else ''}\n"
                    f"- **正确答案**：{err['correct_answer']}\n"
                    f"- **解析**：{err['explanation'] or '暂无解析'}\n"
                    f"- **错误次数**：{err['wrong_count']} 次\n"
                    f"- **最近出错**：{err['last_wrong_at']}\n"
                )

        if exam_errors:
            context_parts.append("## 考试错题")
            for exam in exam_errors:
                context_parts.append(
                    f"### 考试：{exam['exam_title']}\n"
                    f"- 得分：{exam['score']}/{exam['max_score']}\n"
                    f"- 提交时间：{exam['submitted_at']}\n"
                )
                for j, q in enumerate(exam["wrong_questions"], 1):
                    context_parts.append(
                        f"**错题 {j}**：{q.get('stem', '')}\n"
                        f"- 你的答案：{q.get('user_answer', '')}\n"
                        f"- 正确答案：{q.get('correct_answer', '')}\n"
                        f"- 类型：{q.get('type', '')}\n"
                        f"- AI评语：{q.get('ai_comment', '')}\n"
                    )

        # 统计信息
        total_training = len(training_summary)
        total_exam_wrong = sum(len(e["wrong_questions"]) for e in exam_errors)
        total_exam_count = len(exam_errors)
        stat_lines = [
            "## 📊 数据概览",
            f"- **训练错题总数**：{total_training} 道",
            f"- **考试错题总数**：{total_exam_wrong} 道（涉及 {total_exam_count} 场考试）",
        ]
        if category_stats:
            cat_str = "、".join([f"{k}：{v}题" for k, v in category_stats.items()])
            stat_lines.append(f"- **错题分类分布**：{cat_str}")

        stat_block = "\n".join(stat_lines)

        # 构建完整的上下文
        full_context = "\n\n".join([
            stat_block,
            *context_parts,
        ])

        time_hint = ""
        if days == 7:
            time_hint = "本周（近7天）"
        elif days == 30:
            time_hint = "本月（近30天）"
        else:
            time_hint = "所有时间"

        exam_hint = f"关于「{exam_name}」" if exam_name else ""

        report_prompt = (
            f"你是小e，一个专业的英语学习辅导助手。\n\n"
            f"请根据以下学生{time_hint}{exam_hint}的错题数据，生成一份**精美、详尽**的错题总结报告。\n\n"
            f"## 要求\n"
            f"1. 报告格式：纯 Markdown，排版美观，使用标题层级、列表、加粗、分隔线等\n"
            f"2. 结构要求：\n"
            f"   - 📊 数据概览（简要统计）\n"
            f"   - 📝 错题详情（逐题列出，每题包含：题目、你的答案/选项、正确答案、**详细解析**）\n"
            f"   - 🔍 错因分析（按知识点/题型归纳错误模式）\n"
            f"   - 🎯 学习建议（针对错误类型给出具体、可操作的建议）\n"
            f"3. 每题都要包含**详细的题目解析**，解释为什么正确答案是对的\n"
            f"4. 语言：以中文为主，讲解清晰亲切\n"
            f"5. 语气：鼓励、积极，同时给出实质性的改进指导\n"
            f"6. **学习建议要具体**，不要笼统地说「多练习」，而要给出具体练习方向和方法\n\n"
            f"## 错题数据\n\n"
            f"{full_context}\n\n"
            f"请开始生成报告，注意排版精美、内容完整。"
        )

        messages_for_llm = [
            {"role": "user", "content": report_prompt},
        ]
        report = await AIService.chat_completion(db, messages_for_llm, user_id, max_tokens=4096)
        return report.strip()

    @staticmethod
    async def get_student_weakness_analysis(
        db: AsyncSession,
        user_id: int,
        days: int = 30,
    ) -> dict:
        """分析单个学生的薄弱知识点"""
        from app.models.quiz import WrongQuestion

        since_date = datetime.now() - timedelta(days=days)
        stmt = select(
            WrongQuestion.knowledge_point,
            func.count(WrongQuestion.id).label("count"),
        ).where(
            WrongQuestion.user_id == user_id,
            WrongQuestion.last_wrong_at >= since_date,
            WrongQuestion.mastered == 0,
        ).group_by(WrongQuestion.knowledge_point)

        result = await db.execute(stmt)
        weak_points = []
        for row in result.all():
            if row[0]:
                weak_points.append({"knowledge_point": row[0], "error_count": row[1]})

        weak_points.sort(key=lambda x: x["error_count"], reverse=True)

        return {
            "user_id": user_id,
            "total_weak_points": len(weak_points),
            "weak_points": weak_points[:10],
        }

    @staticmethod
    async def find_student_in_class(
        db: AsyncSession,
        class_id: int,
        student_name: str,
    ) -> dict | None:
        """在班级中按昵称/用户名查找学生

        Args:
            db: 数据库会话
            class_id: 班级ID
            student_name: 学生昵称或用户名（模糊匹配）

        Returns:
            {"user_id": int, "nickname": str, "username": str} 或 None
        """
        from app.models.user import User
        from app.models.class_models import ClassStudent

        # 查找班级中的学生ID列表
        student_ids_stmt = select(ClassStudent.student_id).where(
            ClassStudent.class_id == class_id
        )
        result = await db.execute(student_ids_stmt)
        student_ids = [row[0] for row in result.all()]

        if not student_ids:
            return None

        # 在这些学生中按昵称或用户名模糊匹配
        stmt = select(User.id, User.nickname, User.username).where(
            User.id.in_(student_ids),
            User.role == "student",
            or_(
                User.nickname.like(f"%{student_name}%"),
                User.username.like(f"%{student_name}%"),
            ),
        ).limit(5)

        result = await db.execute(stmt)
        matches = result.all()

        if not matches:
            return None

        # 优先精确匹配
        best = None
        for row in matches:
            uid, nick, uname = row[0], row[1] or "", row[2] or ""
            if nick == student_name or uname == student_name:
                best = {"user_id": uid, "nickname": nick, "username": uname}
                break

        if not best:
            row = matches[0]
            best = {"user_id": row[0], "nickname": row[1] or "", "username": row[2] or ""}

        return best

    @staticmethod
    async def find_student_across_classes(
        db: AsyncSession,
        teacher_id: int,
        student_name: str,
    ) -> dict | None:
        """在老师管理的所有班级中查找学生

        Args:
            db: 数据库会话
            teacher_id: 教师ID
            student_name: 学生昵称或用户名（模糊匹配）

        Returns:
            {"user_id": int, "nickname": str, "username": str, "class_id": int, "class_name": str} 或 None
        """
        from app.models.user import User
        from app.models.class_models import Class, ClassStudent, ClassTeacher

        # 获取老师管理的所有班级
        # 方式1: ClassTeacher 关联表
        ct_stmt = select(ClassTeacher.class_id).where(
            ClassTeacher.teacher_id == teacher_id
        )
        ct_result = await db.execute(ct_stmt)
        class_ids_from_ct = [row[0] for row in ct_result.all()]

        # 方式2: Class.created_by
        cb_stmt = select(Class.id).where(Class.created_by == teacher_id)
        cb_result = await db.execute(cb_stmt)
        class_ids_from_cb = [row[0] for row in cb_result.all()]

        all_class_ids = list(set(class_ids_from_ct + class_ids_from_cb))
        if not all_class_ids:
            return None

        # 获取所有班级的学生ID
        cs_stmt = select(ClassStudent.student_id, ClassStudent.class_id).where(
            ClassStudent.class_id.in_(all_class_ids)
        )
        cs_result = await db.execute(cs_stmt)
        class_student_map = {}  # student_id -> class_id
        all_student_ids = []
        for row in cs_result.all():
            sid, cid = row[0], row[1]
            class_student_map[sid] = cid
            all_student_ids.append(sid)

        if not all_student_ids:
            return None

        # 在学生中按昵称或用户名模糊匹配
        stmt = select(User.id, User.nickname, User.username).where(
            User.id.in_(all_student_ids),
            User.role == "student",
            or_(
                User.nickname.like(f"%{student_name}%"),
                User.username.like(f"%{student_name}%"),
            ),
        ).limit(5)

        result = await db.execute(stmt)
        matches = result.all()

        if not matches:
            return None

        # 优先精确匹配
        best = None
        for row in matches:
            uid, nick, uname = row[0], row[1] or "", row[2] or ""
            if nick == student_name or uname == student_name:
                best = {"user_id": uid, "nickname": nick, "username": uname}
                break

        if not best:
            row = matches[0]
            best = {"user_id": row[0], "nickname": row[1] or "", "username": row[2] or ""}

        # 获取该学生所在班级
        matched_class_id = class_student_map.get(best["user_id"])
        if matched_class_id:
            cls = await db.get(Class, matched_class_id)
            best["class_id"] = matched_class_id
            best["class_name"] = cls.name if cls else f"班级{matched_class_id}"
        else:
            # fallback: 取第一个匹配的班级
            best["class_id"] = all_class_ids[0]
            best["class_name"] = ""

        return best

    @staticmethod
    async def generate_student_error_report_for_teacher(
        db: AsyncSession,
        teacher_id: int,
        class_id: int | None,
        student_name: str,
        days: int = 7,
    ) -> dict:
        """教师端：为指定学生生成错题总结报告

        完整的端到端流程：
        1. 查找学生 → 2. 收集错题 → 3. 统计分析 → 4. LLM生成报告

        Args:
            db: 数据库会话
            teacher_id: 教师ID（用于权限校验 + 报告归属）
            class_id: 班级ID（可选，为None时自动搜索所有班级）
            student_name: 学生昵称或用户名
            days: 时间范围天数

        Returns:
            {
                "found": bool,
                "student_info": dict | None,
                "report": str | None,
                "stats": dict | None,
                "error": str | None,
            }
        """
        from app.models.quiz import WrongQuestion, QuestionBank
        from app.models.exam_models import ExamSubmission, TeacherExam
        from app.models.class_models import Class, ClassStudent
        from app.models.scan_models import WrongQuestionBook

        # 1. 查找学生
        if class_id:
            # 指定班级：直接在该班级查找
            student = await RAGService.find_student_in_class(db, class_id, student_name)
        else:
            # 未指定班级：在老师所有班级中查找
            student = await RAGService.find_student_across_classes(db, teacher_id, student_name)

        if not student:
            hint = "该班级中" if class_id else "所有班级中"
            return {
                "found": False,
                "student_info": None,
                "report": None,
                "stats": None,
                "error": f"在{hint}未找到昵称或用户名包含「{student_name}」的学生。请确认学生姓名是否正确。",
            }

        student_id = student["user_id"]
        display_name = student["nickname"] or student["username"] or str(student_id)
        # 使用找到的班级ID
        effective_class_id = class_id or student.get("class_id", 0)

        # 2. 获取班级名
        cls = await db.get(Class, effective_class_id)
        class_name = cls.name if cls else (student.get("class_name") or f"班级{effective_class_id}")

        # 3. 查询训练错题（days>0 时才加时间过滤，0=不限时间查所有）
        since_date = None
        if days > 0:
            since_date = datetime.now() - timedelta(days=days)

        wq_conditions = [
            WrongQuestion.user_id == student_id,
            WrongQuestion.mastered == 0,
        ]
        if since_date:
            wq_conditions.append(WrongQuestion.last_wrong_at >= since_date)

        wq_stmt = select(
            WrongQuestion, QuestionBank.content, QuestionBank.type,
            QuestionBank.stage,
        ).join(
            QuestionBank, WrongQuestion.question_id == QuestionBank.id,
            isouter=True,
        ).where(
            *wq_conditions
        ).order_by(WrongQuestion.last_wrong_at.desc()).limit(30)

        wq_result = await db.execute(wq_stmt)
        training_errors = wq_result.all()

        # 4. 查询考试错题（从 wrong_question_book 表 + ExamSubmission）
        # 扫描批改的 grading_status 包含 omr_done/omr_ext/omr_ext4/omr_real/manual_done
        VALID_GRADING_STATUS = [
            "ai_done", "teacher_reviewed", "pending",
            "omr_done", "omr_ext", "omr_ext4", "omr_real", "manual_done",
        ]

        exam_errors = []
        exam_map = {}  # 提前初始化，确保后续代码可用
        sub_conditions = [
            ExamSubmission.student_id == student_id,
            ExamSubmission.grading_status.in_(VALID_GRADING_STATUS),
        ]
        if since_date:
            sub_conditions.append(ExamSubmission.submitted_at >= since_date)

        sub_stmt = select(ExamSubmission).where(
            *sub_conditions
        ).order_by(ExamSubmission.submitted_at.desc()).limit(20)

        sub_result = await db.execute(sub_stmt)
        submissions = sub_result.scalars().all()

        if submissions:
            exam_ids = list(set(s.exam_id for s in submissions))
            exam_stmt = select(TeacherExam).where(TeacherExam.id.in_(exam_ids))
            exam_result = await db.execute(exam_stmt)
            exam_map = {e.id: e for e in exam_result.scalars().all()}

            for sub in submissions:
                exam = exam_map.get(sub.exam_id)
                if not exam:
                    continue
                grade_detail = sub.ai_grade_detail or []
                wrong_qs = []
                for q in grade_detail:
                    if isinstance(q, dict):
                        is_correct = q.get("is_correct", False)
                        if not is_correct and q.get("score", 0) < q.get("max_score", 1) * 0.7:
                            wrong_qs.append(q)

                if wrong_qs:
                    exam_errors.append({
                        "exam_title": exam.title,
                        "exam_id": exam.id,
                        "score": sub.score,
                        "max_score": sub.max_score,
                        "submitted_at": str(sub.submitted_at)[:10] if sub.submitted_at else "",
                        "wrong_questions": wrong_qs[:10],
                    })

        # 4b. 同时查询 wrong_question_book 表（扫描批改错题的主表）
        # 注意：不按 effective_class_id 过滤，因为 exam.class_id 可能与 student 的 roster class_id 不同
        wqb_conditions = [WrongQuestionBook.student_id == student_id]
        if since_date:
            wqb_conditions.append(WrongQuestionBook.created_at >= since_date)

        wqb_stmt = select(WrongQuestionBook).where(
            *wqb_conditions
        ).order_by(WrongQuestionBook.created_at.desc()).limit(50)

        wqb_result = await db.execute(wqb_stmt)
        wqb_records = wqb_result.scalars().all()

        logger.info(
            f"[generate_student_error_report] 学生={student_name}(id={student_id}), "
            f"WrongQuestionBook记录数={len(wqb_records)}, "
            f"训练错题数={len(training_errors)}, "
            f"ExamSubmission数={len(submissions)}"
        )

        # 按试卷分组 wrong_question_book 记录
        wqb_by_exam = {}
        for wqb in wqb_records:
            eid = wqb.exam_id
            if eid not in wqb_by_exam:
                exam_obj = exam_map.get(eid)
                if not exam_obj:
                    exam_obj = await db.get(TeacherExam, eid)
                wqb_by_exam[eid] = {
                    "exam": exam_obj,
                    "wrong_questions": [],
                    "latest_created_at": wqb.created_at,
                }
            # 将错题记录添加到对应试卷的错题列表
            wqb_by_exam[eid]["wrong_questions"].append(wqb)
            if wqb.created_at and wqb.created_at > wqb_by_exam[eid]["latest_created_at"]:
                wqb_by_exam[eid]["latest_created_at"] = wqb.created_at

        # 如果 wrong_question_book 有数据，优先使用（数据更完整）
        if wqb_records:
            # 查询相关 submission 获取得分信息
            wqb_submission_ids = list(set(wqb.submission_id for wqb in wqb_records))
            wqb_sub_stmt = select(ExamSubmission).where(
                ExamSubmission.id.in_(wqb_submission_ids)
            )
            wqb_sub_result = await db.execute(wqb_sub_stmt)
            wqb_sub_map = {s.id: s for s in wqb_sub_result.scalars().all()}

            exam_errors_from_wqb = []
            for eid, data in wqb_by_exam.items():
                exam_obj = data["exam"]
                if not exam_obj:
                    continue
                wrong_qs = []
                total_score = 0
                total_max = 0
                for wqb in data["wrong_questions"]:
                    wrong_qs.append({
                        "index": wqb.question_index - 1,  # 转为0-based
                        "question_type": wqb.question_type,
                        "stem": wqb.question_stem or "",
                        "user_answer": wqb.student_answer or "",
                        "correct_answer": wqb.correct_answer or "",
                        "score": wqb.score,
                        "max_score": wqb.max_score,
                        "knowledge_point": wqb.knowledge_point or "",
                        "error_category": wqb.error_category or "",
                        "ai_comment": wqb.ai_comment or "",
                        "is_correct": False,
                    })
                    # 从 submission 获取总分
                    sub = wqb_sub_map.get(wqb.submission_id)
                    if sub:
                        total_score = sub.score or 0
                        total_max = sub.max_score or 0
                exam_errors_from_wqb.append({
                    "exam_title": exam_obj.title,
                    "exam_id": exam_obj.id,
                    "score": total_score,
                    "max_score": total_max,
                    "submitted_at": str(data["latest_created_at"])[:10] if data.get("latest_created_at") else "",
                    "wrong_questions": wrong_qs,
                })
            exam_errors = exam_errors_from_wqb

        # 5. 统计数据
        category_stats = {}
        knowledge_stats = {}
        training_summary = []

        for row in training_errors:
            wq = row[0]
            qb_content = row[1] if row[1] else {}
            if isinstance(qb_content, str):
                try:
                    qb_content = json.loads(qb_content)
                except (json.JSONDecodeError, TypeError):
                    qb_content = {}

            training_summary.append({
                "category": wq.category or "其他",
                "knowledge_point": wq.knowledge_point or "未知",
                "stem": qb_content.get("stem", qb_content.get("question", "")),
                "correct_answer": qb_content.get("correct", qb_content.get("answer", "")),
                "options": qb_content.get("options", []),
                "explanation": qb_content.get("explanation", qb_content.get("analysis", "")),
                "wrong_count": wq.wrong_count,
                "question_type": wq.question_type,
                "last_wrong_at": str(wq.last_wrong_at)[:10] if wq.last_wrong_at else "",
            })

            cat = wq.category or "其他"
            category_stats[cat] = category_stats.get(cat, 0) + 1
            kp = wq.knowledge_point or "未知"
            knowledge_stats[kp] = knowledge_stats.get(kp, 0) + 1

        # 也统计 wrong_question_book 的知识点分布
        for wqb in wqb_records:
            kp = wqb.knowledge_point or "未知"
            knowledge_stats[kp] = knowledge_stats.get(kp, 0) + 1
            cat = wqb.error_category or "考试错题"
            category_stats[cat] = category_stats.get(cat, 0) + 1

        category_stats = dict(sorted(category_stats.items(), key=lambda x: x[1], reverse=True))
        knowledge_stats = dict(sorted(knowledge_stats.items(), key=lambda x: x[1], reverse=True))

        total_training = len(training_summary)
        total_exam_wrong = sum(len(e["wrong_questions"]) for e in exam_errors)
        total_exam_count = len(exam_errors)

        logger.info(
            f"[generate_student_error_report] 统计结果: total_training={total_training}, "
            f"total_exam_wrong={total_exam_wrong}, total_exam_count={total_exam_count}"
        )

        # 6. 如果没有任何错题
        if total_training == 0 and total_exam_wrong == 0:
            if days <= 0:
                time_label = "所有历史"
            else:
                time_labels = {7: "本周", 30: "本月", 90: "近三个月"}
                time_label = time_labels.get(days, f"近{days}天")
            return {
                "found": True,
                "student_info": {
                    "user_id": student_id,
                    "display_name": display_name,
                    "class_name": class_name,
                },
                "report": f"## 📊 {display_name}的错题总结\n\n"
                         f"**{time_label}数据**：{display_name}同学在{time_label}内没有未掌握的错题记录，表现优秀！\n\n"
                         f"建议继续保持当前的学习节奏。",
                "stats": {
                    "total_training": 0,
                    "total_exam_wrong": 0,
                    "total_exam_count": 0,
                    "category_distribution": {},
                    "top_knowledge_points": [],
                },
                "error": None,
            }

        # 7. 构建 LLM 上下文
        context_parts = []

        # 数据概览
        time_display = f"近{days}天" if days > 0 else "所有历史"
        stat_lines = [
            f"## 📊 {display_name}的数据概览",
            f"- 学生：{display_name}",
            f"- 班级：{class_name}",
            f"- 时间范围：{time_display}",
            f"- 训练错题：{total_training} 道",
            f"- 考试错题：{total_exam_wrong} 道（涉及 {total_exam_count} 场考试）",
        ]
        if category_stats:
            cat_str = "、".join([f"{k}：{v}题" for k, v in category_stats.items()])
            stat_lines.append(f"- 错题分类：{cat_str}")
        if knowledge_stats:
            top_kp = list(knowledge_stats.items())[:5]
            kp_str = "、".join([f"{k}({v}次)" for k, v in top_kp])
            stat_lines.append(f"- 高频错题知识点：{kp_str}")

        context_parts.append("\n".join(stat_lines))

        # 训练错题详情
        if training_summary:
            context_parts.append("## 训练错题详情")
            for i, err in enumerate(training_summary, 1):
                opts_str = ""
                if err["options"]:
                    letters = ["A", "B", "C", "D", "E", "F"]
                    opts_str = "\n".join(
                        f"  {letters[j]}. {opt}" for j, opt in enumerate(err["options"])
                    )
                context_parts.append(
                    f"### {i}. [{err['category']}] {err['knowledge_point']}\n"
                    f"- 题目：{err['stem']}\n"
                    f"{'- 选项：' + chr(10) + opts_str if opts_str else ''}"
                    f"- 正确答案：{err['correct_answer']}\n"
                    f"- 解析：{err['explanation'] or '暂无解析'}\n"
                    f"- 错误次数：{err['wrong_count']}次\n"
                )

        # 考试错题详情
        if exam_errors:
            context_parts.append("## 考试错题详情")
            for exam in exam_errors:
                context_parts.append(
                    f"### 考试：{exam['exam_title']}\n"
                    f"- 得分：{exam['score']}/{exam['max_score']}\n"
                    f"- 时间：{exam['submitted_at']}\n"
                )
                for j, q in enumerate(exam["wrong_questions"], 1):
                    kp = q.get('knowledge_point', '')
                    ec = q.get('error_category', '')
                    kp_tag = f"（{kp}）" if kp else ""
                    ec_tag = f" [{ec}]" if ec else ""
                    context_parts.append(
                        f"**错题{j}**{kp_tag}{ec_tag}：{q.get('stem', '')}\n"
                        f"- 学生答案：{q.get('user_answer', '')}\n"
                        f"- 正确答案：{q.get('correct_answer', '')}\n"
                        f"- 得分：{q.get('score', 0)}/{q.get('max_score', 0)}\n"
                        f"- AI评语：{q.get('ai_comment', '')}\n"
                    )

        # 7. 构建详细上下文（不调用 LLM，由 chat 流程统一调用，避免双重 LLM 延迟）
        time_labels = {7: "本周（近7天）", 30: "本月（近30天）", 90: "近三个月"}
        time_label = time_labels.get(days, f"近{days}天")

        # 生成报告标题和指令，合并到上下文中一起返回
        report_instruction = (
            f"## 🎯 学生错题报告指令\n\n"
            f"请根据以下{display_name}同学在 **{time_label}** 的错题数据，生成一份专业详尽的错题总结报告。\n\n"
            f"**必须严格按以下格式要求生成：**\n"
            f"1. 📊 数据概览（简要统计）\n"
            f"2. 📝 错题详情——**逐题列出**，每题必须包含：\n"
            f"   - 题目内容\n"
            f"   - 学生选择的答案\n"
            f"   - 正确答案\n"
            f"   - 得分情况\n"
            f"   - AI评语/错因分析\n"
            f"3. 🔍 错因分析（按知识点/题型归纳）\n"
            f"4. 🎯 教学建议（具体可执行的辅导建议）\n\n"
            f"**注意：不要只给标签或分类，必须把每道错题的题目、学生答案、正确答案和分析都展示出来！**\n"
        )
        full_context = report_instruction + "\n\n" + "\n\n".join(context_parts)

        return {
            "found": True,
            "student_info": {
                "user_id": student_id,
                "display_name": display_name,
                "class_name": class_name,
            },
            "report": full_context,
            "stats": {
                "total_training": total_training,
                "total_exam_wrong": total_exam_wrong,
                "total_exam_count": total_exam_count,
                "category_distribution": category_stats,
                "top_knowledge_points": list(knowledge_stats.items())[:5],
            },
            "error": None,
        }
