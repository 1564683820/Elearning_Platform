# 教材点读 Model
# 表清单:
#   textbook_page       教材页面表
#   textbook_unit       教材单元表（用于选择页层级展示）
from sqlalchemy import (
    Column, BigInteger, Integer, String, Text, JSON, DateTime, Index,
    UniqueConstraint, func,
)
from app.db.database import Base
from app.utils.snowflake import next_id


# 教材单元表：存储教材的单元结构，用于层级选择页展示
class TextbookUnit(Base):
    __tablename__ = "textbook_unit"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    textbook_version = Column(String(64), nullable=False, comment="教材版本 e.g. PEP")
    grade = Column(String(16), nullable=False, comment="年级 e.g. 3,4,5,6")
    semester = Column(String(8), default="上", comment="学期: 上/下")
    unit_number = Column(String(16), nullable=False, comment="单元号 e.g. Unit1, Recycle1")
    title = Column(String(128), default="", comment="单元标题")
    sub_title = Column(String(128), default="", comment="副标题")
    cover_image = Column(String(512), default="", comment="单元封面图 URL")
    page_start = Column(Integer, default=1, comment="起始页码")
    page_end = Column(Integer, default=1, comment="结束页码")
    sort_order = Column(Integer, default=0, comment="排序")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("textbook_version", "grade", "semester", "unit_number",
                         name="uk_textbook_unit"),
        Index("idx_version_grade", "textbook_version", "grade"),
        {"mysql_charset": "utf8mb4", "comment": "教材单元表"},
    )


# 教材页面表：存储页面的课文、插图、音频、分句、单词等点读数据
class TextbookPage(Base):
    __tablename__ = "textbook_page"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    unit_id = Column(BigInteger, default=None, comment="关联单元ID(textbook_unit.id)")
    textbook_version = Column(String(64), nullable=False, comment="教材版本 e.g. PEP")
    grade = Column(String(16), nullable=False, comment="年级")
    semester = Column(String(8), default="上", comment="学期")
    unit_number = Column(String(16), nullable=False, comment="单元号")
    page_number = Column(Integer, nullable=False, comment="页码")

    text_content = Column(Text, nullable=False, comment="课文文字全文")
    # 分句 JSON，包含 en/cn/start_sec/end_sec/speaker/animation_url 等字段
    sentences_json = Column(JSON, default=None, comment="分句 [{en,cn,start_sec,end_sec,speaker,animation_url}]")

    image_url = Column(String(512), default="", comment="静态插图 URL")
    image_thumbnail = Column(String(512), default="", comment="缩略图 URL")
    animation_url = Column(String(512), default="", comment="微动图 URL(Lottie/GIF, 整页)")
    background_anim_url = Column(String(512), default="", comment="背景持续微动图 URL（动态图书增强）")
    audio_url = Column(String(512), default="", comment="课文朗读音频 URL")
    audio_duration = Column(Integer, default=0, comment="音频时长(秒)")

    words_json = Column(JSON, default=None, comment="页面单词列表 [{word,phonetic,translation,audio_url}]")
    exercises_json = Column(JSON, default=None, comment="页面练习题(optional)")

    is_active = Column(Integer, default=1, comment="是否启用 0/1")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("textbook_version", "grade", "semester", "unit_number", "page_number",
                         name="uk_textbook_page"),
        Index("idx_unit", "unit_id"),
        Index("idx_version_grade", "textbook_version", "grade"),
        {"mysql_charset": "utf8mb4", "comment": "教材页面表"},
    )
