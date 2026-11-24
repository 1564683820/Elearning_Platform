"""Serialize teaching-assistant sends and look up previously committed replies."""
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatConversation, ChatMessage
from app.services import chat_attachments


class ChatRequestError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


async def lock_conversation(db: AsyncSession, teacher_id: int, conversation_id: int) -> ChatConversation:
    scope = (
        ChatConversation.id == conversation_id, ChatConversation.user_id == teacher_id, ChatConversation.type == 4,
    )
    if await db.scalar(select(ChatConversation.id).where(*scope)) is None:
        raise ChatRequestError(404, "对话会话不存在或无权访问")
    query = select(ChatConversation).where(*scope).with_for_update(nowait=True)
    try:
        conversation = await db.scalar(query)
    except OperationalError as error:
        # MySQL returns ER_LOCK_NOWAIT when another request is answering in the same conversation.
        if error.orig.args and error.orig.args[0] == 3572:
            raise ChatRequestError(409, "这个会话正在回答，请稍后重试") from error
        raise
    if conversation is None:
        raise ChatRequestError(404, "对话会话不存在或无权访问")
    return conversation


async def find_question(db: AsyncSession, conversation_id: int, request_id: str) -> ChatMessage | None:
    return await db.scalar(select(ChatMessage).where(
        ChatMessage.conversation_id == conversation_id, ChatMessage.role == "user", ChatMessage.request_id == request_id,
    ).with_for_update())


async def find_reply(db: AsyncSession, question: ChatMessage) -> ChatMessage | None:
    return await db.scalar(select(ChatMessage).where(
        ChatMessage.conversation_id == question.conversation_id, ChatMessage.role == "assistant",
        ChatMessage.reply_to_message_id == question.id,
    ).with_for_update())


def result(question: ChatMessage, reply: ChatMessage) -> dict:
    return {
        "conversation_id": str(question.conversation_id), "user_message_id": str(question.id),
        "message_id": str(reply.id), "content": reply.content, "sources": reply.sources or [],
        "intent": "", "suggested_questions": [],
    }


async def start(
    db: AsyncSession, teacher_id: int, conversation_id: int, message: str, message_type: str,
    attachment_ids: list[int], request_id: str | None,
) -> tuple[ChatMessage, dict | None]:
    if request_id is not None:
        previous = await find_question(db, conversation_id, request_id)
        if previous is not None:
            linked = await chat_attachments.for_messages(db, teacher_id, [previous.id], lock=True)
            previous_ids = sorted(int(item["attachment_id"]) for item in linked.get(previous.id, []))
            if previous.content != message or previous.message_type != message_type or previous_ids != sorted(attachment_ids):
                raise ChatRequestError(409, "该请求已用于其他问题或附件")
            reply = await find_reply(db, previous)
            if reply is None:
                raise ChatRequestError(409, "该问题尚未完成，请稍后查询")
            return previous, result(previous, reply)

    question = ChatMessage(
        conversation_id=conversation_id, role="user", content=message, message_type=message_type, request_id=request_id,
    )
    db.add(question)
    await db.flush()
    await chat_attachments.bind(db, teacher_id, question.id, attachment_ids)
    return question, None
