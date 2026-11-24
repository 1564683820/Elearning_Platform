from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.api.deps import get_current_user_id
from app.services.favorite_service import FavoriteService
from app.schemas.common import ResponseData, FavoriteCreate, FavoriteOut
from pydantic import BaseModel

router = APIRouter(prefix="/favorites", tags=["收藏"])


@router.get("/", response_model=ResponseData[dict])
async def list_favorites(
    target_type: str = Query("", description="类型: word/article/segment/song"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """收藏列表"""
    result = await FavoriteService.list_favorites(db, user_id, target_type, page, page_size)
    return ResponseData(data=result)


@router.post("/", response_model=ResponseData[FavoriteOut])
async def add_favorite(
    body: FavoriteCreate,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """添加收藏"""
    result = await FavoriteService.add_favorite(db, user_id, body)
    return ResponseData(data=result)


@router.delete("/{favorite_id:int}", response_model=ResponseData[dict])
async def remove_favorite(
    favorite_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """取消收藏"""
    result = await FavoriteService.remove_favorite(db, user_id, favorite_id)
    return ResponseData(data=result)


class BatchDeleteBody(BaseModel):
    ids: list[int]


@router.delete("/batch", response_model=ResponseData[dict])
async def batch_remove_favorites(
    body: BatchDeleteBody,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """批量取消收藏"""
    result = await FavoriteService.batch_remove_favorites(db, user_id, body.ids)
    return ResponseData(data=result)


@router.get("/check", response_model=ResponseData[dict])
async def check_favorite(
    target_type: str = Query(..., description="类型"),
    target_id: int = Query(..., description="目标ID"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """检查是否已收藏"""
    result = await FavoriteService.check_favorite(db, user_id, target_type, target_id)
    return ResponseData(data=result)
