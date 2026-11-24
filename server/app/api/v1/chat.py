from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.api.deps import get_current_user_id
from app.services.chat_service import ChatService, ChatSessionNotFoundError, ChatGenerationError
from app.schemas.common import (
    ResponseData, ChatSessionCreate, ChatConversationOut, ChatSendRequest,
)

router = APIRouter(prefix="/chat", tags=["对话"])


@router.get("/sessions", response_model=ResponseData[dict])
async def list_sessions(
    chat_type: int = Query(0, description="1=情景对话,2=智能问答,3=智能翻译"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """对话会话列表"""
    result = await ChatService.list_sessions(db, user_id, chat_type, page, page_size)
    return ResponseData(data=result)


@router.post("/sessions", response_model=ResponseData[ChatConversationOut])
async def create_session(
    body: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """创建对话会话"""
    result = await ChatService.create_session(db, user_id, body)
    return ResponseData(data=result)


@router.get("/sessions/{session_id}/messages", response_model=ResponseData[dict])
async def get_messages(
    session_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """获取会话消息历史"""
    try:
        result = await ChatService.get_session_messages(db, session_id, user_id, page, page_size)
    except ChatSessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return ResponseData(data=result)


@router.post("/sessions/{session_id}/send", response_model=ResponseData[dict])
async def send_message(
    session_id: int,
    body: ChatSendRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """发送消息（AI回复）"""
    try:
        result = await ChatService.send_message(db, session_id, user_id, body)
    except ChatSessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ChatGenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return ResponseData(data=result)


@router.post("/sessions/{session_id}/evaluate", response_model=ResponseData[dict])
async def evaluate_dialogue(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """情景对话评价"""
    try:
        result = await ChatService.evaluate_dialogue(db, session_id, user_id)
    except ChatSessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return ResponseData(data=result)
