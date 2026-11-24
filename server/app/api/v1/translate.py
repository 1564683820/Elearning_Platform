from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.api.deps import get_current_user_id
from app.services.ai_service import AIService
from app.schemas.common import ResponseData, TranslateRequest, TranslateResponse

router = APIRouter(prefix="/translate", tags=["翻译"])


@router.post("/", response_model=ResponseData[TranslateResponse])
async def translate_text(
    body: TranslateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """文本翻译"""
    result = await AIService.translate_text(db, body.text, body.source_lang, body.target_lang, user_id)
    return ResponseData(data=TranslateResponse(**result))
