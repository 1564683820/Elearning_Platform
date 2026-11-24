"""PPT 主题与版本历史 ORM 模型"""

from sqlalchemy import (
    Column, BigInteger, Integer, String, Text, JSON, DateTime, Index, func,
)
from app.db.database import Base
from app.utils.snowflake import next_id


class PPTTheme(Base):
    """幻灯片主题表"""
    __tablename__ = "ppt_theme"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    name = Column(String(64), nullable=False, comment="主题标识名（如 classic, cartoon）")
    display_name = Column(String(128), nullable=False, comment="主题显示名（如 经典简约）")
    description = Column(String(256), default="", comment="主题描述")
    css_variables = Column(Text, nullable=False, comment="CSS 变量定义（:root {...}）")
    css_content = Column(Text, nullable=False, comment="完整主题 CSS 内容")
    preview_color = Column(String(32), default="#2d7d46", comment="预览色")
    preview_url = Column(String(512), default="", comment="预览截图URL")
    sort_order = Column(Integer, default=0, comment="排序号")
    is_builtin = Column(Integer, default=1, comment="是否为内置主题")
    teacher_id = Column(BigInteger, default=None, comment="自定义主题创建教师ID")
    style_skill = Column(JSON, default=None, comment="设计规范: color_scheme/typography/layout_rules等")
    slide_layouts = Column(JSON, default=None, comment="各slide类型的推荐布局映射")
    font_pairings = Column(JSON, default=None, comment="字体配对列表")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_theme_name", "name"),
        Index("idx_theme_builtin", "is_builtin"),
        Index("idx_theme_teacher", "teacher_id"),
        {"mysql_charset": "utf8mb4", "comment": "幻灯片主题表"},
    )


class PptVersion(Base):
    """幻灯片版本历史表"""
    __tablename__ = "ppt_version"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    ppt_id = Column(BigInteger, nullable=False, comment="关联的 PPT ID")
    version = Column(Integer, nullable=False, comment="版本号")
    html_content = Column(Text, nullable=False, comment="该版本的 HTML 完整内容")
    pages_json = Column(JSON, default=None, comment="该版本的 JSON 页面数据")
    theme_name = Column(String(64), default="", comment="该版本使用的主题")
    change_summary = Column(String(512), default="", comment="变更摘要")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_v_ppt", "ppt_id"),
        Index("idx_v_ppt_version", "ppt_id", "version"),
        {"mysql_charset": "utf8mb4", "comment": "幻灯片版本历史表"},
    )
