"""AI 视频教材演绎 API 路由"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.api.deps import get_current_user_id
from app.schemas.video import VideoGenerateRequest, CHARACTER_TYPE_MAP
from app.schemas.common import ResponseData
from pydantic import BaseModel, Field
from app.schemas.common import ResponseData
from app.services.video_ai_service import VideoAIService

router = APIRouter(prefix="/video", tags=["AI视频教材演绎"])


# ========== 预设角色 ==========

@router.get("/characters", response_model=ResponseData)
async def list_characters(
    db: AsyncSession = Depends(get_db),
):
    """获取所有预设角色列表"""
    chars = await VideoAIService.list_characters(db)
    return ResponseData(data=chars)


# ========== 视频生成 ==========

# ========== AI 分镜脚本生成（预览用） ==========

class GenerateScriptRequest(BaseModel):
    """预制脚本生成请求（从 Mini Program 直接调用）"""
    text_content: str = Field(..., description="课文文字内容")
    character_name: str = Field("小猫老师", description="角色名称")


@router.post("/generate-script", response_model=ResponseData)
async def preview_generate_script(
    body: GenerateScriptRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """AI 生成分镜脚本预览"""
    if not body.text_content.strip():
        raise HTTPException(status_code=400, detail="课文内容不能为空")
    script = await VideoAIService.generate_script(
        db=db,
        text_content=body.text_content,
        character_name=body.character_name,
        user_id=user_id,
    )
    return ResponseData(data=script)


# ========== 视频生成 ==========

@router.post("/generate", response_model=ResponseData)
async def create_video(
    body: VideoGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """创建 AI 视频教材演绎任务"""
    if body.character_type not in CHARACTER_TYPE_MAP and body.character_type != "custom":
        raise HTTPException(
            status_code=400,
            detail=f"不支持的角色类型: {body.character_type}，可选: {list(CHARACTER_TYPE_MAP.keys())} + custom",
        )
    if not body.text_content.strip():
        raise HTTPException(status_code=400, detail="课文内容不能为空")
    if body.character_type == "custom" and not body.character_image_url:
        raise HTTPException(status_code=400, detail="自定义角色必须上传角色图片")

    try:
        result = await VideoAIService.create_video_task(
            db=db,
            user_id=user_id,
            title=body.title,
            textbook_version=body.textbook_version,
            textbook_grade=body.textbook_grade,
            textbook_semester=body.textbook_semester,
            unit_id=body.unit_id,
            unit_name=body.unit_name,
            page_ids=body.page_ids,
            text_content=body.text_content,
            character_type=body.character_type,
            character_image_url=body.character_image_url,
        )
        return ResponseData(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========== 视频 CRUD ==========

@router.get("/list", response_model=ResponseData)
async def list_videos(
    status: Optional[str] = Query(None, description="筛选状态"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """获取用户的 AI 视频列表"""
    result = await VideoAIService.list_videos(db, user_id, status, page, page_size)
    return ResponseData(data=result)


@router.get("/{video_id}", response_model=ResponseData)
async def get_video(
    video_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """获取单个视频详情"""
    result = await VideoAIService.get_video(db, video_id, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="视频不存在")
    return ResponseData(data=result)


@router.delete("/{video_id}", response_model=ResponseData)
async def delete_video(
    video_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """删除视频"""
    success = await VideoAIService.delete_video(db, video_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="视频不存在")
    return ResponseData(message="删除成功")


@router.get("/{video_id}/status", response_model=ResponseData)
async def get_video_status(
    video_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """查询视频生成状态（供轮询使用）"""
    result = await VideoAIService.get_video_status(db, video_id, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="视频不存在")
    return ResponseData(data=result)


# ========== 收藏 ==========

@router.post("/{video_id}/favorite", response_model=ResponseData)
async def toggle_favorite(
    video_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """切换视频收藏状态"""
    result = await VideoAIService.toggle_favorite(db, video_id, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="视频不存在")
    return ResponseData(data=result)
