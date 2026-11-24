from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_words_db, get_db
from app.api.deps import get_current_user_id
from app.services.word_service import WordService
from app.schemas.common import (
    ResponseData, PaginatedResponse, WordOut, WordDetail,
    WordProgressCreate, WordListQuery,
)

router = APIRouter(prefix="/words", tags=["单词"])


@router.get("/", response_model=PaginatedResponse[WordOut])
async def list_words(
    search: str = Query("", description="搜索单词"),
    stage: int = Query(0, description="学习阶段 1-13，0=不限"),
    tag: str = Query("", description="考试标签筛选，如 cet4/cet6/zk/gk，为空时不限制"),
    sort_by: str = Query("importance", description="排序: asc=升序, desc=倒序, importance=重要度, random=随机"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_words_db),
):
    """单词列表（分页、搜索、阶段筛选、标签筛选、排序）"""
    query = WordListQuery(search=search, stage=stage, tag=tag, sort_by=sort_by, page=page, page_size=page_size)
    result = await WordService.list_words(db, query)
    return PaginatedResponse(data=result)


@router.get("/daily", response_model=ResponseData[list[WordOut]])
async def daily_words(
    stage: int = Query(5, description="学习阶段 1-13"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_words_db),
):
    """今日推荐单词列表"""
    result = await WordService.get_daily_words(db, stage, limit)
    return ResponseData(data=result)


@router.get("/{word_id}", response_model=ResponseData[WordDetail])
async def get_word_detail(
    word_id: int,
    db: AsyncSession = Depends(get_words_db),
    main_db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """单词详情（含词根、近义词、学习进度）"""
    result = await WordService.get_word_detail(db, word_id, user_id, main_db)
    return ResponseData(data=result)


@router.get("/search/{word_text}", response_model=ResponseData[WordDetail])
async def search_word(
    word_text: str,
    db: AsyncSession = Depends(get_words_db),
    main_db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """按单词文本搜索单词详情"""
    result = await WordService.get_word_by_name(db, word_text, user_id, main_db)
    return ResponseData(data=result)


@router.post("/{word_id}/progress", response_model=ResponseData[dict])
async def record_progress(
    word_id: int,
    body: WordProgressCreate,
    db: AsyncSession = Depends(get_words_db),
    user_id: int = Depends(get_current_user_id),
):
    """记录学习进度"""
    result = await WordService.record_progress(db, user_id, word_id, body.mastery_level)
    return ResponseData(data=result)


@router.get("/{word_id}/neighbor", response_model=ResponseData[dict])
async def get_neighbor_word(
    word_id: int,
    direction: str = Query("next", description="prev/next"),
    stage: int = Query(0, description="学习阶段 1-13，0=不限"),
    db: AsyncSession = Depends(get_words_db),
):
    """获取相邻单词ID"""
    neighbor_id = await WordService.get_neighbor_word_id(db, word_id, direction, stage)
    return ResponseData(data={"word_id": neighbor_id})
