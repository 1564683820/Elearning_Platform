"""
教学助手 API 路由 — 支持会话管理、流式/非流式对话、文件上传

端点清单：
  GET    /teaching-assistant/sessions              会话列表
  POST   /teaching-assistant/sessions              创建新会话
  GET    /teaching-assistant/sessions/{id}/messages 获取消息
  DELETE /teaching-assistant/sessions/{id}          删除(归档)会话
  POST   /teaching-assistant/chat                  非流式对话
  POST   /teaching-assistant/chat/stream            SSE 流式对话
  POST   /teaching-assistant/upload                 上传图片/附件
  GET    /teaching-assistant/memory                 获取长期记忆
  DELETE /teaching-assistant/memory/{id}            删除记忆
  POST   /teaching-assistant/memory/extract         从对话提取记忆
"""

import json
import os
from app.core.paths import UPLOADS_DIR
import uuid
import logging
from contextlib import aclosing
from typing import Optional
from anyio import CancelScope
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query, Body, Path
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.api.deps import get_current_teacher_id, get_current_user_id
from app.services.teaching_assistant_service import TeachingAssistantService
from app.services import chat_attachments
from app.services import chat_requests
from app.services.exam_knowledge import has_exam_knowledge
from app.services.private_document_files import MAX_FILE_BYTES, PrivateFileError
from app.services.memory_service import MemoryService
from app.schemas.common import ResponseData
from app.schemas.exam_knowledge import ExamKnowledgeAvailability

router = APIRouter(prefix="/teaching-assistant", tags=["教学助手"])
logger = logging.getLogger(__name__)

# 上传文件保存目录
UPLOAD_DIR = str(UPLOADS_DIR / "teaching_assistant")


# ==================== 会话管理 ====================

@router.get("/exam-knowledge/availability", response_model=ResponseData[ExamKnowledgeAvailability])
async def exam_knowledge_availability(
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    return ResponseData(data=ExamKnowledgeAvailability(has_confirmed_results=await has_exam_knowledge(db, teacher_id)))


@router.get("/sessions", response_model=ResponseData)
async def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取教学助手会话列表"""
    result = await TeachingAssistantService.list_sessions(db, teacher_id, page, page_size)
    return ResponseData(data=result)


@router.post("/sessions", response_model=ResponseData)
async def create_session(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """创建新的教学助手会话"""
    class_id = body.get("class_id")
    if class_id is not None:
        class_id = int(class_id)
    result = await TeachingAssistantService.create_session(db, teacher_id, class_id)
    return ResponseData(data=result)


class BatchDeleteSessionsRequest(BaseModel):
    """批量删除会话请求"""
    session_ids: list[int]


@router.delete("/sessions/batch", response_model=ResponseData)
async def batch_delete_sessions(
    body: BatchDeleteSessionsRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """批量删除会话（硬删除，同时清除向量数据库中的记录）"""
    if not body.session_ids:
        raise HTTPException(status_code=400, detail="session_ids 不能为空")
    deleted = await TeachingAssistantService.batch_delete_sessions(
        db, body.session_ids, teacher_id,
    )
    return ResponseData(data={"deleted": deleted}, message=f"已清除 {deleted} 个会话")


@router.get("/sessions/{session_id}/messages", response_model=ResponseData)
async def get_session_messages(
    session_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    latest: bool = Query(False, description="从最新消息读取，再按时间正序返回本页"),
    before_id: int | None = Query(None, gt=0, description="读取此会话内指定消息之前的记录"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取会话消息历史"""
    try:
        result = await TeachingAssistantService.get_session_messages(
            db, session_id, teacher_id, page, page_size, latest=latest, before_id=before_id,
        )
        return ResponseData(data=result)
    except ValueError as e:
        logger.warning(f"获取消息失败 session_id={session_id} teacher_id={teacher_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取消息异常 session_id={session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取消息失败")


@router.delete("/sessions/{session_id}", response_model=ResponseData)
async def delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """删除（归档）会话"""
    await TeachingAssistantService.delete_session(db, session_id, teacher_id)
    return ResponseData(message="已归档")


# ==================== 对话 ====================

class ChatRequest(BaseModel):
    """教学助手对话请求"""
    conversation_id: Optional[int] = None
    message: str
    class_id: Optional[int] = None
    message_type: str = "text"
    attachment_ids: list[int] = Field(default_factory=list, max_length=chat_attachments.MAX_ATTACHMENTS)
    request_id: str | None = Field(None, pattern=r"^[a-z0-9_-]{1,64}$")


class ChatStreamingResponse(StreamingResponse):
    async def stream_response(self, send):
        # Closing the body also covers cancellation while awaiting ASGI send.
        async with aclosing(self.body_iterator):
            await super().stream_response(send)


@router.get("/sessions/{session_id}/requests/{request_id}", response_model=ResponseData)
async def read_chat_request(
    session_id: int,
    response: Response,
    request_id: str = Path(pattern=r"^[a-z0-9_-]{1,64}$"),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """Look up the committed reply for this question in the teacher's own session."""
    response.headers["Cache-Control"] = "private, no-store"
    try:
        await chat_requests.lock_conversation(db, teacher_id, session_id)
    except chat_requests.ChatRequestError as error:
        if error.status == 409:
            await db.rollback()
            return ResponseData(data={"status": "pending"})
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    question = await chat_requests.find_question(db, session_id, request_id)
    reply = await chat_requests.find_reply(db, question) if question is not None else None
    if reply is not None:
        return ResponseData(data={"status": "completed", "reply": chat_requests.result(question, reply)})
    return ResponseData(data={"status": "pending" if question is not None else "unknown"})


@router.post("/chat", response_model=ResponseData)
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """非流式教学助手对话"""
    if body.request_id and not body.conversation_id:
        raise HTTPException(status_code=422, detail="带重试标识的问题必须关联会话")
    try:
        result = await TeachingAssistantService.chat(
            db=db,
            teacher_id=teacher_id,
            message=body.message,
            conversation_id=body.conversation_id,
            class_id=body.class_id,
            message_type=body.message_type,
            attachment_ids=body.attachment_ids,
            request_id=body.request_id,
        )
    except (PrivateFileError, chat_requests.ChatRequestError) as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    return ResponseData(data=result)


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """SSE 流式教学助手对话"""
    if body.request_id and not body.conversation_id:
        raise HTTPException(status_code=422, detail="带重试标识的问题必须关联会话")
    async def stream():
        try:
            async with aclosing(TeachingAssistantService.chat_stream(
                db=db, teacher_id=teacher_id, message=body.message, conversation_id=body.conversation_id,
                class_id=body.class_id, message_type=body.message_type,
                attachment_ids=body.attachment_ids, request_id=body.request_id,
            )) as messages:
                async for message in messages:
                    yield message
        finally:
            # The assistant commits only complete turns. Drop any uncommitted question/attachments.
            with CancelScope(shield=True):
                await db.close()

    return ChatStreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )


# ==================== 文件上传 ====================

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_DOC_TYPES = {
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
}


@router.post("/upload", response_model=ResponseData)
async def upload_file(
    file: UploadFile = File(...),
    structured: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """上传图片或附件到教学助手对话"""
    if structured:
        try:
            result = await chat_attachments.upload(db, teacher_id, file.filename or "", await file.read(MAX_FILE_BYTES + 1))
        except PrivateFileError as error:
            raise HTTPException(status_code=error.status, detail=str(error)) from error
        return ResponseData(data=result)
    # 验证文件类型
    content_type = file.content_type or ""
    is_image = content_type in ALLOWED_IMAGE_TYPES
    is_doc = content_type in ALLOWED_DOC_TYPES

    if not is_image and not is_doc:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {content_type}")

    # 创建保存目录
    teacher_dir = os.path.join(UPLOAD_DIR, str(teacher_id))
    os.makedirs(teacher_dir, exist_ok=True)

    # 生成唯一文件名
    ext = os.path.splitext(file.filename or "file")[1] or ".bin"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(teacher_dir, unique_name)

    # 保存文件
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    file_size = len(content)
    file_url = f"/uploads/teaching_assistant/{teacher_id}/{unique_name}"

    result = {
        "file_url": file_url,
        "file_name": file.filename,
        "file_size": file_size,
        "file_type": "image" if is_image else "document",
        "content_type": content_type,
    }

    return ResponseData(data=result)


@router.get("/attachments/{attachment_id}")
async def download_attachment(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    try:
        path, filename, mime = await chat_attachments.download(db, teacher_id, attachment_id)
    except PrivateFileError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    return FileResponse(path, filename=filename, media_type=mime, headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


# ==================== 长期记忆 ====================

@router.get("/memory", response_model=ResponseData)
async def list_memories(
    memory_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """获取教师的长期记忆列表"""
    result = await MemoryService.list_memories(db, teacher_id, memory_type, page, page_size)
    return ResponseData(data=result)


@router.delete("/memory/{memory_id}", response_model=ResponseData)
async def delete_memory(
    memory_id: int,
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """删除指定长期记忆"""
    ok = await MemoryService.delete_memory(db, memory_id, teacher_id)
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return ResponseData(message="已删除")


@router.post("/memory/extract", response_model=ResponseData)
async def extract_memory(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    teacher_id: int = Depends(get_current_teacher_id),
):
    """从指定对话中自动提取长期记忆"""
    conversation_id = body.get("conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="需要 conversation_id")
    memories = await MemoryService.auto_create_from_conversation(
        db, teacher_id, int(conversation_id),
    )
    return ResponseData(data={"created": len(memories)})
