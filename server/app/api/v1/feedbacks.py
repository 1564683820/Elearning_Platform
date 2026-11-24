from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.api.deps import get_current_user_id
from app.models.stats import Feedback
from app.schemas.common import ResponseData, FeedbackCreate

router = APIRouter(prefix="/feedbacks", tags=["反馈"])


@router.post("/", response_model=ResponseData[dict])
async def submit_feedback(
    body: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """提交反馈"""
    feedback = Feedback(
        user_id=user_id,
        type=body.type,
        content=body.content,
        screenshot_url=body.screenshot_url,
    )
    db.add(feedback)
    await db.flush()
    return ResponseData(data={"message": "感谢您的反馈！"})
