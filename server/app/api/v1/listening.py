from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.services.quiz_service import QuizService
from app.schemas.common import ResponseData

router = APIRouter(prefix="/listening", tags=["听力"])


@router.get("/", response_model=ResponseData[dict])
async def list_listening_materials(
    stage: int = Query(0, description="学习阶段 1-13，0=不限"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """听力材料列表"""
    result = await QuizService.list_listening_materials(db, stage, page, page_size)
    return ResponseData(data=result)


@router.get("/{material_id}", response_model=ResponseData[dict])
async def get_listening_detail(
    material_id: int,
    db: AsyncSession = Depends(get_db),
):
    """听力材料详情+题目"""
    result = await QuizService.get_listening_detail(db, material_id)
    return ResponseData(data=result)
