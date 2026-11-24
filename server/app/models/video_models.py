"""AI 视频教材演绎 ORM 模型"""
from sqlalchemy import (
    Column, BigInteger, Integer, String, JSON, Text, DateTime, Index, func,
)
from app.db.database import Base
from app.utils.snowflake import next_id


class PresetCharacter(Base):
    """预设角色表：视频演绎的默认角色（小猫老师、Kevin、Emma、博士猫头鹰）"""
    __tablename__ = "preset_character"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    character_key = Column(String(32), nullable=False, unique=True, comment="角色标识")
    name = Column(String(64), nullable=False, comment="角色显示名称")
    description = Column(String(256), default="", comment="角色描述")
    image_url = Column(Text, default=None, comment="角色预设图片URL")
    voice_type = Column(String(32), default="", comment="TTS音色类型")
    sort_order = Column(Integer, default=0, comment="排序")
    is_active = Column(Integer, default=1, comment="是否启用: 1启用 0禁用")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    __table_args__ = (
        Index("idx_pc_active", "is_active"),
        {"mysql_charset": "utf8mb4", "comment": "视频演绎预设角色表"},
    )


class AiVideo(Base):
    """AI视频记录表：用户生成的教材演绎视频"""
    __tablename__ = "ai_video"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="创建用户ID")
    title = Column(String(256), default="", comment="视频标题")
    textbook_version = Column(String(32), default="", comment="教材版本")
    textbook_grade = Column(String(16), default="", comment="年级")
    textbook_semester = Column(String(16), default="", comment="学期")
    unit_id = Column(BigInteger, default=None, comment="关联教材单元ID")
    unit_name = Column(String(128), default="", comment="单元名称")
    page_ids = Column(JSON, default=None, comment="选中的教材页面ID列表")
    text_content = Column(Text, default=None, comment="课文文字内容（用于配音）")
    character_type = Column(String(32), nullable=False, default="cat_teacher", comment="角色类型")
    character_image_url = Column(Text, default=None, comment="自定义角色图片URL")
    script_json = Column(JSON, default=None, comment="AI生成的分镜脚本JSON")
    tts_audio_url = Column(Text, default=None, comment="TTS配音音频URL")
    video_url = Column(Text, default=None, comment="最终合成视频URL（CDN）")
    thumbnail_url = Column(Text, default=None, comment="视频缩略图URL")
    subtitle_url = Column(Text, default=None, comment="字幕文件URL")
    duration = Column(Integer, default=0, comment="视频时长（秒）")
    status = Column(String(16), nullable=False, default="pending", comment="状态: pending/processing/completed/failed")
    error_message = Column(Text, default=None, comment="失败原因")
    view_count = Column(Integer, default=0, comment="观看次数")
    favorite_count = Column(Integer, default=0, comment="收藏次数")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_av_user", "user_id"),
        Index("idx_av_status", "status"),
        Index("idx_av_unit", "unit_id"),
        Index("idx_av_created", "created_at"),
        {"mysql_charset": "utf8mb4", "comment": "AI视频教材演绎记录表"},
    )
