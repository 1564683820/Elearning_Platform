"""备课 PPT 与课堂互动 ORM 模型"""
from sqlalchemy import (
    Column, BigInteger, Integer, String, JSON, Text, DateTime, Index, func,
)
from app.db.database import Base
from app.utils.snowflake import next_id


class LessonPPT(Base):
    """备课 PPT 主表：教师创建的互动 PPT，含页面 JSON + HTML 双格式"""
    __tablename__ = "lesson_ppt"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    teacher_id = Column(BigInteger, nullable=False, comment="创建教师ID")
    class_id = Column(BigInteger, default=None, comment="目标班级ID（可为空）")
    knowledge_graph_id = Column(BigInteger, default=None, comment="关联知识图谱 ID")
    title = Column(String(256), nullable=False, comment="PPT 标题")
    lesson_type = Column(String(32), nullable=False, comment="课型: new_lesson/review/exercise/conversation")
    subject = Column(String(128), default="", comment="主题/单元")
    grade = Column(String(16), default="", comment="适用年级")
    stage_category = Column(String(16), default="other",
        comment="学段: preschool/primary/junior/senior/other")
    outline = Column(JSON, default=None, comment="AI 生成的大纲")
    pages_json = Column(JSON, nullable=False, comment="所有页面内容 JSON")
    html_content = Column(Text, default=None, comment="完整 HTML 格式幻灯片（含主题 CSS）")
    theme_name = Column(String(64), default="classic", comment="当前主题名")
    version = Column(Integer, default=1, comment="版本号")
    thumbnail_url = Column(String(512), default="", comment="缩略图URL")
    slide_count = Column(Integer, default=0, comment="幻灯片页数")
    interaction_config = Column(JSON, default=None, comment="互动配置")
    layout_intent = Column(String(32), default="auto", comment="布局意图: auto/cover/data_focus等")
    transition_type = Column(String(16), default="slide", comment="页面切换动画: fade/slide/push")
    transition_duration = Column(Integer, default=400, comment="切换动画时长(ms)")
    layout_overrides = Column(JSON, default=None, comment="各slide type的布局覆盖")
    spec_lock = Column(JSON, default=None, comment="设计规格锁定 Phase3.3（视觉风格/配色/字体/布局/节奏）")
    status = Column(String(16), default="draft", comment="状态: draft/published/archived")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_ppt_teacher", "teacher_id"),
        Index("idx_ppt_class", "class_id"),
        Index("idx_ppt_status", "status"),
        {"mysql_charset": "utf8mb4", "comment": "备课PPT主表"},
    )


class ClassroomSession(Base):
    """课堂会话表：记录授课过程中的实时互动数据"""
    __tablename__ = "classroom_session"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    ppt_id = Column(BigInteger, nullable=False, comment="关联的 PPT ID")
    teacher_id = Column(BigInteger, nullable=False, comment="授课教师ID")
    title = Column(String(256), default="", comment="课堂标题")
    status = Column(String(16), default="active", comment="状态: active/paused/ended")
    current_page = Column(Integer, default=0, comment="当前播放页索引")
    student_count = Column(Integer, default=0, comment="参与学生数")
    interaction_data = Column(JSON, default=None, comment="互动汇总数据")
    started_at = Column(DateTime, nullable=False, comment="课堂开始时间")
    ended_at = Column(DateTime, default=None, comment="课堂结束时间")

    __table_args__ = (
        Index("idx_ws_ppt", "ppt_id"),
        Index("idx_ws_teacher", "teacher_id"),
        Index("idx_ws_status", "status"),
        {"mysql_charset": "utf8mb4", "comment": "课堂会话表"},
    )
