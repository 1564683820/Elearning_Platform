import random
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, exists
from app.models.quiz import QuestionBank, ReadingMaterial, ListeningMaterial, UserQuizLog, WrongQuestion, TrainingSession
from app.models.stats import LearningBehaviorLog
from app.schemas.common import (
    QuizGenerateRequest, QuestionOut, QuizSubmitRequest, QuizSubmitResponse,
)
from app.services.ai_service import AIService
from app.services.stats_service import StatsService
from app.services.grading_result import validate_grade_result

# 填空/开放题题型（不走题库，纯 AI 生成）
AI_ONLY_TYPES = {8, 9}


class QuizService:

    @staticmethod
    async def generate_questions(db: AsyncSession, req: QuizGenerateRequest, user_id: int | None = None) -> list[QuestionOut]:
        """生成训练题目：仅从题库抽题（选择题型），填空/开放题走AI"""
        questions = []

        # 填空/开放题（type 8/9）直接走 AI 生成，不走题库
        ai_only_types = [t for t in req.question_types if t in AI_ONLY_TYPES]
        db_types = [t for t in req.question_types if t not in AI_ONLY_TYPES]

        # 从题库取选择题
        for q_type in db_types:
            stmt = select(QuestionBank).where(
                QuestionBank.type == q_type,
                QuestionBank.is_active == 1,
            )
            if req.stage:
                # 同时用 stage 字段和 tag 关键字匹配（通过 word_id 关联 dict_word）
                from app.services.word_service import STAGE_TAG_MAP
                from app.models.word import DictWord
                tag_keywords = STAGE_TAG_MAP.get(req.stage)
                if tag_keywords:
                    tag_conditions = [
                        DictWord.tag.like(f"%{kw}%") for kw in tag_keywords
                    ]
                    tag_exists = (
                        exists(
                            select(DictWord.id).where(
                                DictWord.id == QuestionBank.word_id,
                                or_(*tag_conditions),
                            )
                        )
                    )
                    stmt = stmt.where(
                        or_(QuestionBank.stage == req.stage, tag_exists)
                    )
                else:
                    # stage 1-4（BNC 基础阶段）或未知阶段：使用已有 stage 字段
                    stmt = stmt.where(QuestionBank.stage == req.stage)

            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = (await db.execute(count_stmt)).scalar() or 0

            if total > 0:
                offset = random.randint(0, max(0, total - req.count))
                stmt = stmt.offset(offset).limit(req.count)
                result = await db.execute(stmt)
                db_questions = result.scalars().all()
                questions.extend([QuestionOut.model_validate(q) for q in db_questions])

        # 填空/开放题：直接 AI 生成
        if ai_only_types and user_id:
            ai_fill_questions = await AIService.generate_quiz_questions(
                db, user_id, ai_only_types, req.stage,
                req.count,
                options_mode="fill_in",
            )
            questions.extend(ai_fill_questions)

        return questions[:req.count]

    # 题型到分类的映射
    _TYPE_CATEGORY_MAP = {
        1: "vocabulary",
        2: "translation",
        3: "listening",
        4: "grammar",
        5: "translation",
        6: "reading",
        7: "listening",
        8: "translation",  # 句子翻译（填空）
        9: "writing",      # 作文写作
    }

    @staticmethod
    def _get_category(question_type: int) -> str:
        """根据题型返回错题分类"""
        return QuizService._TYPE_CATEGORY_MAP.get(question_type, "vocabulary")

    @staticmethod
    async def submit_answer(db: AsyncSession, user_id: int, req: QuizSubmitRequest) -> QuizSubmitResponse:
        """提交答案：判题、记录、错题入库，支持分类标记"""
        # 处理 AI 生成的开放题（负 ID，无 DB 记录）
        if req.question_id < 0:
            return QuizSubmitResponse(
                is_correct=True,
                correct_answer=req.answer,
            )

        result = await db.execute(select(QuestionBank).where(QuestionBank.id == req.question_id))
        question = result.scalar_one_or_none()
        if not question:
            raise ValueError("题目不存在")

        content = question.content if isinstance(question.content, dict) else {}
        correct_answer = content.get("correct", content.get("correctIndex", content.get("answer")))

        # 填空/开放题（type 8/9）：不自动判题，直接记录并返回参考
        if question.type in (8, 9):
            is_correct = True
            # 记录答题日志
            log = UserQuizLog(
                user_id=user_id,
                question_id=req.question_id,
                question_type=question.type,
                is_correct=1,
                user_answer={"answer": req.answer, "reference": content.get("reference", "")},
                time_spent=req.time_spent,
            )
            db.add(log)
            await db.flush()
            return QuizSubmitResponse(
                is_correct=True,
                correct_answer=content.get("reference", ""),
                analysis={
                    "explanation": content.get("reference", ""),
                    "reference": content.get("reference", ""),
                    "type_hint": content.get("type_hint", "fill_in"),
                }
            )

        is_correct = str(req.answer) == str(correct_answer)

        # 记录答题日志
        log = UserQuizLog(
            user_id=user_id,
            question_id=req.question_id,
            question_type=question.type,
            is_correct=1 if is_correct else 0,
            user_answer={"answer": req.answer},
            time_spent=req.time_spent,
        )
        db.add(log)

        # 分析错题分类和知识点
        category = QuizService._get_category(question.type)
        knowledge_point = content.get("knowledge_point", content.get("tags", ""))

        # 答错则加入错题本（含分类和知识点标记）
        if not is_correct:
            mistake_result = await db.execute(
                select(WrongQuestion).where(
                    WrongQuestion.user_id == user_id,
                    WrongQuestion.question_id == req.question_id,
                )
            )
            mistake = mistake_result.scalar_one_or_none()
            if mistake:
                mistake.wrong_count += 1
                mistake.mastered = 0
                mistake.last_wrong_at = datetime.now()
                if category:
                    mistake.category = category
                if knowledge_point:
                    mistake.knowledge_point = knowledge_point
            else:
                mistake = WrongQuestion(
                    user_id=user_id,
                    question_id=req.question_id,
                    question_type=question.type,
                    category=category,
                    knowledge_point=knowledge_point,
                    wrong_count=1,
                    last_wrong_at=datetime.now(),
                )
                db.add(mistake)

            # 将错题索引到 RAG 系统
            content_text = content.get("stem", content.get("question", ""))
            if content_text:
                try:
                    from app.services.rag_service import RAGService
                    await RAGService.index_wrong_question_for_rag(
                        db, user_id, question.id, content_text,
                        question.type, category, knowledge_point, str(question.stage),
                    )
                except Exception as e:
                    # RAG 索引失败不影响主流程
                    print(f"RAG index failed for question {question.id}: {e}")

        # 记录学习行为日志
        try:
            behavior_log = LearningBehaviorLog(
                user_id=user_id,
                action_type="submit_answer",
                target_type="question",
                target_id=req.question_id,
                detail={
                    "is_correct": is_correct,
                    "question_type": question.type,
                    "category": category,
                },
                session_duration=req.time_spent,
            )
            db.add(behavior_log)
        except Exception:
            pass

        # 更新每日统计
        await StatsService.increment_quiz_stat(db, user_id, is_correct)

        await db.flush()

        # 构建解析
        analysis = None
        if isinstance(content, dict):
            analysis = {
                "explanation": content.get("explanation", content.get("analysis", "")),
                "correct_answer": correct_answer,
            }

        return QuizSubmitResponse(
            is_correct=is_correct,
            correct_answer=correct_answer,
            analysis=analysis,
        )

    @staticmethod
    async def get_mistakes(
        db: AsyncSession, user_id: int, question_type: int = 0,
        mastered: int | None = None, page: int = 1, page_size: int = 20
    ) -> dict:
        """错题本列表"""
        stmt = select(WrongQuestion).where(WrongQuestion.user_id == user_id)

        if question_type:
            stmt = stmt.where(WrongQuestion.question_type == question_type)
        if mastered is not None:
            stmt = stmt.where(WrongQuestion.mastered == mastered)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(WrongQuestion.last_wrong_at.desc()).offset(offset).limit(page_size)
        result = await db.execute(stmt)
        mistakes = result.scalars().all()

        # 关联题目详情
        items = []
        for m in mistakes:
            q_result = await db.execute(select(QuestionBank).where(QuestionBank.id == m.question_id))
            q = q_result.scalar_one_or_none()
            items.append({
                "id": m.id,
                "question_id": m.question_id,
                "question_type": m.question_type,
                "wrong_count": m.wrong_count,
                "last_wrong_at": str(m.last_wrong_at),
                "mastered": m.mastered,
                "created_at": str(m.created_at),
                "question": QuestionOut.model_validate(q) if q else None,
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    async def review_mistake(db: AsyncSession, user_id: int, mistake_id: int, mastered: bool) -> dict:
        """错题复习 - 标记掌握/未掌握"""
        result = await db.execute(
            select(WrongQuestion).where(WrongQuestion.id == mistake_id, WrongQuestion.user_id == user_id)
        )
        mistake = result.scalar_one_or_none()
        if not mistake:
            raise ValueError("错题记录不存在")

        mistake.mastered = 1 if mastered else 0
        await db.flush()

        return {"mastered": mistake.mastered, "wrong_count": mistake.wrong_count}

    @staticmethod
    async def get_quiz_stats(db: AsyncSession, user_id: int) -> dict:
        """训练统计数据"""
        total_result = await db.execute(
            select(func.count()).where(UserQuizLog.user_id == user_id)
        )
        total_count = total_result.scalar() or 0

        correct_result = await db.execute(
            select(func.count()).where(
                UserQuizLog.user_id == user_id,
                UserQuizLog.is_correct == 1,
            )
        )
        correct_count = correct_result.scalar() or 0

        mistake_result = await db.execute(
            select(func.count()).where(
                WrongQuestion.user_id == user_id,
                WrongQuestion.mastered == 0,
            )
        )
        mistake_count = mistake_result.scalar() or 0

        accuracy = round(correct_count / total_count * 100, 1) if total_count > 0 else 0

        return {
            "total_count": total_count,
            "correct_count": correct_count,
            "accuracy": accuracy,
            "mistake_count": mistake_count,
        }

    @staticmethod
    async def list_reading_materials(
        db: AsyncSession, stage: int = 0, page: int = 1, page_size: int = 20
    ) -> dict:
        """阅读材料列表"""
        stmt = select(ReadingMaterial)
        if stage:
            stmt = stmt.where(ReadingMaterial.stage == stage)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(ReadingMaterial.id.desc()).offset(offset).limit(page_size)
        result = await db.execute(stmt)
        materials = result.scalars().all()

        return {
            "items": [
                {"id": m.id, "title": m.title, "content": m.content,
                 "content_cn": m.content_cn, "stage": m.stage, "type": m.type,
                 "word_count": m.word_count, "difficulty": m.difficulty, "source": m.source}
                for m in materials
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    async def get_reading_detail(db: AsyncSession, material_id: int) -> dict:
        """阅读材料详情 + 题目"""
        result = await db.execute(select(ReadingMaterial).where(ReadingMaterial.id == material_id))
        material = result.scalar_one_or_none()
        if not material:
            raise ValueError("阅读材料不存在")

        # 关联题目
        q_result = await db.execute(
            select(QuestionBank).where(
                QuestionBank.reading_id == material_id,
                QuestionBank.is_active == 1,
            )
        )
        questions = [QuestionOut.model_validate(q) for q in q_result.scalars().all()]

        return {
            "id": material.id, "title": material.title, "content": material.content,
            "content_cn": material.content_cn,
            "stage": material.stage, "type": material.type,
            "word_count": material.word_count, "difficulty": material.difficulty,
            "questions": questions,
        }

    @staticmethod
    async def list_listening_materials(
        db: AsyncSession, stage: int = 0, page: int = 1, page_size: int = 20
    ) -> dict:
        """听力材料列表"""
        stmt = select(ListeningMaterial)
        if stage:
            stmt = stmt.where(ListeningMaterial.stage == stage)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(ListeningMaterial.id.desc()).offset(offset).limit(page_size)
        result = await db.execute(stmt)
        materials = result.scalars().all()

        return {
            "items": [
                {"id": m.id, "title": m.title, "audio_url": m.audio_url,
                 "duration": m.duration, "stage": m.stage, "type": m.type,
                 "source": m.source}
                for m in materials
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    async def get_listening_detail(db: AsyncSession, material_id: int) -> dict:
        """听力材料详情 + 题目"""
        result = await db.execute(select(ListeningMaterial).where(ListeningMaterial.id == material_id))
        material = result.scalar_one_or_none()
        if not material:
            raise ValueError("听力材料不存在")

        # 关联题目
        q_result = await db.execute(
            select(QuestionBank).where(
                QuestionBank.type == 7,  # 听力训练
                QuestionBank.reading_id == material_id,
                QuestionBank.is_active == 1,
            )
        )
        questions = [QuestionOut.model_validate(q) for q in q_result.scalars().all()]

        return {
            "id": material.id, "title": material.title,
            "audio_url": material.audio_url, "transcript": material.transcript,
            "transcript_cn": material.transcript_cn,
            "duration": material.duration, "stage": material.stage,
            "questions": questions,
        }

    # ═══════════════════════════════════════════════════════════
    # 题库收录机制 — 优先从题库取，取不到则 AI 生成并入库
    # ═══════════════════════════════════════════════════════════

    # AI 题型 → question_bank.type 映射
    _AI_QUESTION_TYPE_MAP = {
        "reading": 6,       # 阅读理解
        "translation": 8,   # 句子翻译（填空）
        "essay": 9,         # 作文写作
    }

    @staticmethod
    async def fetch_ai_question(
        db: AsyncSession, user_id: int,
        qtype: str, stage: int, difficulty: str = "中级"
    ) -> dict:
        """
        从题库获取 AI 生成题目，若全部答过则重新 AI 生成并入库。
        qtype: "reading" / "translation" / "essay"
        返回: dict，包含原 AI 结果 + question_bank_id
        """
        bank_type = QuizService._AI_QUESTION_TYPE_MAP.get(qtype)
        if not bank_type:
            raise ValueError(f"不支持的题型: {qtype}")

        # 1. 查询题库中未答过的题目
        from sqlalchemy import not_, exists
        answered_subq = (
            select(UserQuizLog.question_id).where(
                UserQuizLog.user_id == user_id,
                UserQuizLog.question_type == bank_type,
            ).subquery()
        )
        stmt = select(QuestionBank).where(
            QuestionBank.type == bank_type,
            QuestionBank.is_active == 1,
            QuestionBank.stage == stage,
            not_(QuestionBank.id.in_(answered_subq)),
        ).order_by(func.random()).limit(1)

        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # 从题库已有记录返回
            content = existing.content if isinstance(existing.content, dict) else {}
            if qtype == "reading":
                return {
                    "question_bank_id": existing.id,
                    "title": content.get("article_title", ""),
                    "content": content.get("article_content", ""),
                    "content_cn": content.get("content_cn", ""),
                    "word_count": content.get("word_count", 0),
                    "questions": content.get("questions", []),
                }
            elif qtype == "translation":
                return {
                    "question_bank_id": existing.id,
                    "stem": content.get("stem", ""),
                    "topic": content.get("topic", ""),
                    "key_vocab": content.get("key_vocab", []),
                    "reference": content.get("reference", ""),
                    "hints": content.get("hints", ""),
                }
            elif qtype == "essay":
                return {
                    "question_bank_id": existing.id,
                    "stem": content.get("stem", ""),
                    "topic": content.get("topic", ""),
                    "word_limit": content.get("word_limit", ""),
                    "reference": content.get("reference", ""),
                    "key_points": content.get("key_points", []),
                }

        # 2. 题库中无未答题 → AI 生成后入库
        if qtype == "reading":
            result = await AIService.generate_reading_passage(db, user_id, stage, difficulty)
            if result:
                content = {
                    "article_title": result.get("title", ""),
                    "article_content": result.get("content", ""),
                    "content_cn": result.get("content_cn", ""),
                    "word_count": result.get("word_count", 0),
                    "difficulty": difficulty,
                    "questions": result.get("questions", []),
                }
                qb = QuestionBank(
                    stage=stage, type=bank_type, difficulty=2,
                    content=content, source="ai_generate",
                )
                db.add(qb)
                await db.flush()
                result["question_bank_id"] = qb.id
        elif qtype == "translation":
            result = await AIService.generate_translation_paragraph(db, user_id, stage)
            if result:
                content = {
                    "stem": result.get("stem", ""),
                    "topic": result.get("topic", ""),
                    "key_vocab": result.get("key_vocab", []),
                    "reference": result.get("reference", ""),
                    "hints": result.get("hints", ""),
                }
                qb = QuestionBank(
                    stage=stage, type=bank_type, difficulty=2,
                    content=content, source="ai_generate",
                )
                db.add(qb)
                await db.flush()
                result["question_bank_id"] = qb.id
        elif qtype == "essay":
            result = await AIService.generate_essay_prompt(db, user_id, stage)
            if result:
                content = {
                    "stem": result.get("stem", ""),
                    "topic": result.get("topic", ""),
                    "word_limit": result.get("word_limit", ""),
                    "reference": result.get("reference", ""),
                    "key_points": result.get("key_points", []),
                }
                qb = QuestionBank(
                    stage=stage, type=bank_type, difficulty=2,
                    content=content, source="ai_generate",
                )
                db.add(qb)
                await db.flush()
                result["question_bank_id"] = qb.id
        else:
            result = {}

        # 记录学习行为
        if result:
            try:
                behavior_log = LearningBehaviorLog(
                    user_id=user_id,
                    action_type="fetch_ai_question",
                    target_type=qtype,
                    target_id=result.get("question_bank_id", 0),
                    detail={"stage": stage, "difficulty": difficulty, "source": "bank" if existing else "ai"},
                )
                db.add(behavior_log)
            except Exception:
                pass

        return result

    # ═══════════════════════════════════════════════════════════
    # 新训练体系 — AI 驱动方法（保留旧接口兼容）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def generate_reading(
        db: AsyncSession, user_id: int, stage: int, difficulty: str = "中级"
    ) -> dict:
        """AI 生成阅读文章 + 5 道选择题"""
        result = await AIService.generate_reading_passage(db, user_id, stage, difficulty)

        # 记录学习行为
        try:
            behavior_log = LearningBehaviorLog(
                user_id=user_id,
                action_type="generate_reading",
                target_type="reading",
                detail={
                    "word_count": result.get("word_count", 0),
                    "difficulty": difficulty,
                    "stage": stage,
                },
            )
            db.add(behavior_log)
        except Exception:
            pass

        return result

    @staticmethod
    async def generate_translation(
        db: AsyncSession, user_id: int, stage: int
    ) -> dict:
        """AI 生成翻译练习（中文段落 + 参考答案）"""
        result = await AIService.generate_translation_paragraph(db, user_id, stage)

        # 记录学习行为
        try:
            behavior_log = LearningBehaviorLog(
                user_id=user_id,
                action_type="generate_translation",
                target_type="translation",
                detail={"topic": result.get("topic", ""), "stage": stage},
            )
            db.add(behavior_log)
        except Exception:
            pass

        return result

    @staticmethod
    async def score_translation(
        db: AsyncSession, user_id: int,
        source_text: str, user_answer: str, reference: str,
        question_id: int = 0,
    ) -> dict:
        """AI 评分翻译练习"""
        result = await AIService.score_translation(
            db, user_id, source_text, user_answer, reference
        )

        score = validate_grade_result(result)["score"]

        # 记录答题日志（有 question_bank_id 则用实 ID，否则用负哈希兼容）
        qid = question_id if question_id > 0 else -(hash(source_text[:50]) % 10000 + 1)
        log = UserQuizLog(
            user_id=user_id,
            question_id=qid,
            question_type=8,
            is_correct=1 if score >= 60 else 0,
            user_answer={
                "answer": user_answer,
                "reference": reference,
                "score": score,
                "feedback": result.get("feedback", ""),
            },
            time_spent=0,
        )
        db.add(log)

        # 更新每日统计
        await StatsService.increment_quiz_stat(db, user_id, score >= 60)
        await db.flush()

        return result

    @staticmethod
    async def generate_essay(
        db: AsyncSession, user_id: int, stage: int
    ) -> dict:
        """AI 生成作文题目"""
        result = await AIService.generate_essay_prompt(db, user_id, stage)

        # 记录学习行为
        try:
            behavior_log = LearningBehaviorLog(
                user_id=user_id,
                action_type="generate_essay",
                target_type="essay",
                detail={"topic": result.get("topic", ""), "stage": stage},
            )
            db.add(behavior_log)
        except Exception:
            pass

        return result

    @staticmethod
    async def score_essay(
        db: AsyncSession, user_id: int,
        essay_topic: str, user_answer: str, reference: str,
        question_id: int = 0,
    ) -> dict:
        """AI 评分英语作文"""
        result = await AIService.score_essay(
            db, user_id, essay_topic, user_answer, reference
        )

        score = validate_grade_result(result)["score"]

        # 记录答题日志（有 question_bank_id 则用实 ID，否则用负哈希兼容）
        qid = question_id if question_id > 0 else -(hash(essay_topic[:50]) % 10000 + 20000)
        log = UserQuizLog(
            user_id=user_id,
            question_id=qid,
            question_type=9,
            is_correct=1 if score >= 60 else 0,
            user_answer={
                "answer": user_answer,
                "reference": reference,
                "score": score,
                "feedback": result.get("feedback", ""),
                "dimensions": result.get("dimensions", {}),
            },
            time_spent=0,
        )
        db.add(log)

        # 更新每日统计
        await StatsService.increment_quiz_stat(db, user_id, score >= 60)
        await db.flush()

        return result
