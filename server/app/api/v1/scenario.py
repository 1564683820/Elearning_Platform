from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db, get_words_db
from app.api.deps import get_current_user_id
from app.services.chat_service import ScenarioService
from app.services.video_service import VideoService
from app.schemas.common import ResponseData, ScenarioGenerateRequest, ScenarioOut

router = APIRouter(prefix="/scenario", tags=["情景记忆"])


@router.post("/generate", response_model=ResponseData[dict])
async def generate_scenario(
    body: ScenarioGenerateRequest,
    db: AsyncSession = Depends(get_db),
    words_db: AsyncSession = Depends(get_words_db),
    user_id: int = Depends(get_current_user_id),
):
    """AI生成情景文段"""
    result = await ScenarioService.generate_scenario(
        db, user_id, body.word_ids, body.time_range, body.passage_type, words_db=words_db
    )
    return ResponseData(data=result)


@router.get("/history", response_model=ResponseData[dict])
async def list_scenarios(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """历史生成记录"""
    result = await ScenarioService.list_scenarios(db, user_id, page, page_size)
    return ResponseData(data=result)


@router.post("/{scenario_id}/video", response_model=ResponseData[dict])
async def create_scene_video(
    scenario_id: int,
    db: AsyncSession = Depends(get_db),
    words_db: AsyncSession = Depends(get_words_db),
    user_id: int = Depends(get_current_user_id),
):
    """为情景文段创建记忆视频"""
    from app.models.chat import ScenarioPassage
    from app.models.word import DictWord
    from sqlalchemy import select

    result = await db.execute(
        select(ScenarioPassage).where(ScenarioPassage.id == scenario_id, ScenarioPassage.user_id == user_id)
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise ValueError("情景文段不存在")

    words = []
    if scenario.word_ids:
        word_ids_list = scenario.word_ids if isinstance(scenario.word_ids, list) else []
        if word_ids_list:
            word_result = await words_db.execute(
                select(DictWord).where(DictWord.id.in_(word_ids_list))
            )
            words = [w.word for w in word_result.scalars().all()]

    video_info = await VideoService.generate_scene_video(
        db, user_id, scenario_id, words, scenario.content
    )
    return ResponseData(data=video_info)


@router.get("/video/list", response_model=ResponseData[dict])
async def list_videos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """情景记忆视频列表"""
    result = await VideoService.list_user_videos(db, user_id, page, page_size)
    return ResponseData(data=result)


@router.get("/{scenario_id}/video/status", response_model=ResponseData[dict])
async def get_video_status(
    scenario_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """查询视频生成状态"""
    result = await VideoService.get_video_status(db, user_id, scenario_id)
    return ResponseData(data=result)
