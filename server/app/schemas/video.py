"""AI 视频教材演绎 Pydantic 模型"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ========== 预设角色 ==========

class PresetCharacterOut(BaseModel):
    """预设角色输出模型"""
    id: int
    character_key: str
    name: str
    description: str
    image_url: str
    voice_type: str
    sort_order: int
    is_active: int

    model_config = {"from_attributes": True}


# ========== 视频生成 ==========

class VideoGenerateRequest(BaseModel):
    """AI 视频生成请求"""
    title: str = Field("", max_length=256, description="视频标题")
    textbook_version: str = Field("", max_length=32, description="教材版本")
    textbook_grade: str = Field("", max_length=16, description="年级")
    textbook_semester: str = Field("", max_length=16, description="学期")
    unit_id: Optional[int] = Field(None, description="关联教材单元ID")
    unit_name: str = Field("", max_length=128, description="单元名称")
    page_ids: list[int] = Field(default_factory=list, description="选中的教材页面ID列表")
    text_content: str = Field(..., description="课文文字内容")
    character_type: str = Field("cat_teacher", description="角色类型")
    character_image_url: Optional[str] = Field(None, description="自定义角色图片URL")


class VideoGenerateResult(BaseModel):
    """视频生成结果"""
    id: int
    title: str
    status: str
    created_at: str
    message: str = "视频生成任务已创建"


# ========== 视频记录 ==========

class AiVideoOut(BaseModel):
    """AI 视频输出模型"""
    id: int
    user_id: int
    title: str
    textbook_version: str
    textbook_grade: str
    textbook_semester: str
    unit_id: Optional[int]
    unit_name: str
    text_content: Optional[str]
    character_type: str
    character_image_url: Optional[str]
    script_json: Optional[dict]
    tts_audio_url: Optional[str]
    video_url: Optional[str]
    thumbnail_url: Optional[str]
    subtitle_url: Optional[str]
    duration: int
    status: str
    error_message: Optional[str]
    view_count: int
    favorite_count: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class AiVideoListItem(BaseModel):
    """AI 视频列表项"""
    id: int
    title: str
    textbook_version: str
    textbook_grade: str
    unit_name: str
    character_type: str
    character_type_name: str
    thumbnail_url: Optional[str]
    duration: int
    status: str
    view_count: int
    favorite_count: int
    created_at: str

    model_config = {"from_attributes": True}


# ========== 统一返回常量 ==========

CHARACTER_TYPE_MAP = {
    "cat_teacher": "小猫老师",
    "kevin": "Kevin",
    "emma": "Emma",
    "owl_professor": "博士猫头鹰",
}

CHARACTER_VOICE_MAP = {
    "cat_teacher": "zh-CN-XiaoxiaoNeural",
    "kevin": "zh-CN-YunxiNeural",
    "emma": "zh-CN-XiaoyiNeural",
    "owl_professor": "zh-CN-YunjianNeural",
}
