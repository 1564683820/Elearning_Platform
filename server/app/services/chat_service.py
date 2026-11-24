import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.chat import ChatConversation, ChatMessage, ScenarioPassage
from app.schemas.common import ChatSessionCreate, ChatConversationOut, ChatMessageOut, ChatSendRequest
from app.services.ai_service import AIService
from app.services.rag_service import RAGService
from app.services.embedding_service import EmbeddingService
from app.core.config import get_settings
from datetime import datetime, timedelta

# Agent integration — AI dialogue logic delegated to agent module
# from agent.agents.xiao_e_agent import XiaoEAgent  # uncomment to use agent

settings = get_settings()

CHAT_CONTEXT_MAX_ROUNDS = 10


class ChatSessionNotFoundError(ValueError):
    pass


class ChatGenerationError(ValueError):
    pass


class ChatService:

    @staticmethod
    async def list_sessions(
        db: AsyncSession, user_id: int, chat_type: int = 0, page: int = 1, page_size: int = 20
    ) -> dict:
        """对话会话列表"""
        stmt = select(ChatConversation).where(ChatConversation.user_id == user_id)
        if chat_type:
            stmt = stmt.where(ChatConversation.type == chat_type)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(ChatConversation.created_at.desc()).offset(offset).limit(page_size)
        result = await db.execute(stmt)
        sessions = result.scalars().all()

        return {
            "items": [ChatConversationOut.model_validate(s) for s in sessions],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    async def create_session(db: AsyncSession, user_id: int, data: ChatSessionCreate) -> ChatConversationOut:
        """创建对话会话"""
        session = ChatConversation(
            user_id=user_id,
            type=data.type,
            scene_desc=data.scene_desc,
            user_role=data.user_role,
            title=data.title,
        )
        db.add(session)
        await db.flush()
        await db.refresh(session)
        return ChatConversationOut.model_validate(session)

    @staticmethod
    async def get_session_messages(
        db: AsyncSession, conversation_id: int, user_id: int, page: int = 1, page_size: int = 50
    ) -> dict:
        """获取会话消息历史"""
        session = await ChatService._get_user_session(db, conversation_id, user_id)

        stmt = select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc()).offset(offset).limit(page_size)
        result = await db.execute(stmt)
        messages = result.scalars().all()

        return {
            "items": [ChatMessageOut.model_validate(m) for m in messages],
            "total": total,
            "session": ChatConversationOut.model_validate(session),
        }

    @staticmethod
    async def send_message(
        db: AsyncSession, conversation_id: int, user_id: int, data: ChatSendRequest
    ) -> dict:
        """发送消息并获取AI回复"""
        session = await ChatService._get_user_session(db, conversation_id, user_id)
        messages = []
        if session.type != 2:
            # 数据库为上下文真源，避免 Redis 缺失或事务回滚留下的缓存消息影响对话。
            result = await db.execute(
                select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                .limit(CHAT_CONTEXT_MAX_ROUNDS * 2 - 1)
            )
            messages = [{"role": item.role, "content": item.content}
                        for item in reversed(result.scalars().all())]
        messages.append({"role": "user", "content": data.message})

        # 根据会话类型使用不同策略
        sources = []
        if session.type == 2:  # 智能问答
            rag_result = await RAGService.answer_question(db, data.message, user_id)
            ai_content = rag_result["answer"]
            sources = rag_result.get("sources", [])
        elif session.type == 1:  # 情景对话
            if session.scene_desc:
                system_msg = (
                    f"你是一个英语对话练习伙伴。场景：{session.scene_desc}。用户身份：{session.user_role}。\n"
                    f"请用英语回复，保持对话自然流畅。如果用户用中文回复，温和地引导他们用英语。"
                )
                messages.insert(0, {"role": "system", "content": system_msg})
            ai_content = await AIService.chat_completion(db, messages, user_id)
        else:
            ai_content = await AIService.chat_completion(db, messages, user_id)

        if not isinstance(ai_content, str) or not ai_content.strip():
            raise ChatGenerationError("AI 未返回有效回答，请稍后重试")

        # 生成成功后，在调用方事务中成对保存，不单独提交或发布未提交上下文。
        user_msg = ChatMessage(
            conversation_id=conversation_id, role="user", content=data.message,
            message_type=data.message_type,
        )
        ai_msg = ChatMessage(
            conversation_id=conversation_id,
            role="assistant",
            content=ai_content,
            message_type="text",
            sources=sources if sources else None,
        )
        db.add(user_msg)
        db.add(ai_msg)
        await db.flush()

        return {
            "user_message": ChatMessageOut.model_validate(user_msg),
            "ai_message": ChatMessageOut.model_validate(ai_msg),
        }

    @staticmethod
    async def evaluate_dialogue(db: AsyncSession, conversation_id: int, user_id: int) -> dict:
        """情景对话评价"""
        session = await ChatService._get_user_session(db, conversation_id, user_id)

        result = await db.execute(
            select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )
        messages = result.scalars().all()
        dialogue_text = "\n".join([f"{m.role}: {m.content}" for m in messages])

        prompt = (
            f"请对以下英语对话进行评价，从语法准确性、用词恰当性、表达自然度三个维度打分（1-5星），"
            f"并给出改进建议：\n\n{dialogue_text}\n\n"
            f"请按以下JSON格式返回：\n"
            f'{{"grammar_score": 1-5, "vocabulary_score": 1-5, "fluency_score": 1-5, '
            f'"overall_score": 1-5, "feedback": "总体评价和建议"}}'
        )

        messages_for_ai = [{"role": "user", "content": prompt}]
        evaluation_text = await AIService.chat_completion(db, messages_for_ai, user_id)

        try:
            evaluation = json.loads(evaluation_text.strip())
        except json.JSONDecodeError:
            evaluation = {"overall_score": 0, "feedback": evaluation_text}

        # 保存评价到会话
        session.evaluation = evaluation
        await db.flush()

        return evaluation

    @staticmethod
    async def _get_user_session(db: AsyncSession, conversation_id: int, user_id: int) -> ChatConversation:
        """验证会话归属并返回"""
        result = await db.execute(
            select(ChatConversation).where(ChatConversation.id == conversation_id, ChatConversation.user_id == user_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise ChatSessionNotFoundError("对话会话不存在")
        return session


class ScenarioService:

    @staticmethod
    async def generate_scenario(
        db: AsyncSession, user_id: int,
        word_ids: list[int], time_range: str = "week",
        passage_type: str = "story", stage: int = 0,
        words_db: AsyncSession | None = None,
    ) -> dict:
        """AI生成情景文段"""
        _words_db = words_db or db
        from app.models.word import DictWord
        from sqlalchemy import select as sa_select

        stmt = sa_select(DictWord).where(DictWord.id.in_(word_ids))
        result = await _words_db.execute(stmt)
        words = result.scalars().all()

        if not words:
            raise ValueError("未找到指定单词")

        word_texts = [w.word for w in words]
        # 前端传中文(报道/故事/顺口溜) → 映射为英文 key
        cn_to_en = {'报道': 'news', '故事': 'story', '顺口溜': 'rap'}
        passage_type_en = cn_to_en.get(passage_type, passage_type)
        content = await AIService.generate_scenario(db, user_id, word_texts, passage_type_en, stage)

        # 过期时间 30 天
        expires_at = datetime.now() + timedelta(days=30)

        scenario = ScenarioPassage(
            user_id=user_id,
            word_ids=word_ids,
            passage_type=passage_type,
            content=content,
            expires_at=expires_at,
            model_used=settings.LLM_MODEL,
        )
        db.add(scenario)
        await db.flush()
        await db.refresh(scenario)

        return {
            "id": scenario.id,
            "content": scenario.content,
            "word_ids": scenario.word_ids,
            "passage_type": scenario.passage_type,
            "video_url": scenario.video_url,
            "video_status": scenario.video_status,
            "expires_at": str(scenario.expires_at),
            "created_at": str(scenario.created_at),
        }

    @staticmethod
    async def list_scenarios(
        db: AsyncSession, user_id: int, page: int = 1, page_size: int = 20
    ) -> dict:
        """历史生成记录"""
        stmt = select(ScenarioPassage).where(ScenarioPassage.user_id == user_id)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(ScenarioPassage.created_at.desc()).offset(offset).limit(page_size)
        result = await db.execute(stmt)
        scenarios = result.scalars().all()

        return {
            "items": [
                {"id": s.id, "content": s.content, "word_ids": s.word_ids,
                 "passage_type": s.passage_type, "video_url": s.video_url,
                 "video_status": s.video_status, "created_at": str(s.created_at)}
                for s in scenarios
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
