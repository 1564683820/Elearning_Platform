from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db, get_words_db
from app.api.deps import get_current_user_id
from app.services.stats_service import StatsService
from app.schemas.common import ResponseData, DashboardStats

router = APIRouter(prefix="/stats", tags=["统计"])


@router.get("/dashboard", response_model=ResponseData[DashboardStats])
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    words_db: AsyncSession = Depends(get_words_db),
    user_id: int = Depends(get_current_user_id),
):
    """首页看板数据"""
    result = await StatsService.get_dashboard(db, user_id, words_db=words_db)
    return ResponseData(data=result)


@router.get("/daily", response_model=ResponseData[list[dict]])
async def get_daily_stats(
    start_date: str = Query("", description="开始日期 YYYY-MM-DD"),
    end_date: str = Query("", description="结束日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """按日统计"""
    result = await StatsService.get_daily_stats(db, user_id, start_date, end_date)
    return ResponseData(data=[r.model_dump() for r in result])


@router.get("/weekly", response_model=ResponseData[dict])
async def get_weekly_stats(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """按周统计"""
    result = await StatsService.get_weekly_stats(db, user_id)
    return ResponseData(data=result)
