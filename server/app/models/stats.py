"""
统计 + 文档 + 反馈 Model — 对齐 DBplan 2.10 / 2.11 + 统计

表清单:
  user_daily_stat  每日统计表
  user_document    用户上传文档表
  feedback         用户反馈表
"""
from sqlalchemy import (
    Column, BigInteger, Integer, SmallInteger, String, Text, Date, DateTime, JSON,
    Index, UniqueConstraint, func,
)
from sqlalchemy.dialects.mysql import SMALLINT as MYSQL_SMALLINT
from app.db.database import Base
from app.utils.snowflake import next_id


# ──────────────────────────────────────────────
# 统计模块
# ──────────────────────────────────────────────

class UserDailyStat(Base):
    """每日学习统计表"""
    __tablename__ = "user_daily_stats"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    stat_date = Column(Date, nullable=False, comment="统计日期")
    words_learned = Column(Integer, default=0, comment="学习单词数")
    words_reviewed = Column(Integer, default=0, comment="复习单词数")
    quiz_count = Column(Integer, default=0, comment="做题数")
    quiz_correct = Column(Integer, default=0, comment="正确数")
    study_minutes = Column(Integer, default=0, comment="学习时长(分钟)")

    __table_args__ = (
        Index("uk_user_date", "user_id", "stat_date", unique=True),
        {"mysql_charset": "utf8mb4", "comment": "每日学习统计表"},
    )


# ──────────────────────────────────────────────
# 2.10 文档上传模块
# ──────────────────────────────────────────────

class UserDocument(Base):
    """用户上传文档表（增强版：支持文档分类、学段、自定义标签）"""
    __tablename__ = "user_document"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    filename = Column(String(256), nullable=False, comment="原始文件名")
    file_type = Column(String(16), nullable=False, comment="文件类型: pdf/ppt/word/txt/image")
    file_size = Column(Integer, nullable=False, default=0, comment="文件大小(字节)")
    storage_key = Column(String(512), nullable=False, comment="MinIO/云存储 对象 key")
    parse_status = Column(SmallInteger, default=0, comment="解析状态: 0=待处理,1=解析中,2=已完成,3=失败")
    parsed_text = Column(Text, comment="解析提取的文本内容")
    vector_status = Column(SmallInteger, default=0, comment="向量化状态: 0=未开始,1=进行中,2=已完成,3=失败")
    chunk_count = Column(Integer, default=0, comment="分块数量")
    created_at = Column(DateTime, server_default=func.now())

    # 扩展（兼容旧字段）
    file_path = Column(String(512), default="", comment="本地存储路径(开发用)")
    md_file_path = Column(String(512), default="", comment="MinerU 转换后的 Markdown 文件路径")
    ocr_text = Column(Text, comment="OCR 提取文本(兼容旧字段)")

    # ==== 新增：文档分类与学段 ====
    doc_category = Column(String(32), default="other",
        comment="文档分类: exam/teaching_plan/courseware/textbook/reference/other")
    stage_category = Column(String(16), default="other",
        comment="学段: preschool/primary/junior/senior/other")
    doc_tags = Column(String(255), default="",
        comment="自定义标签，逗号分隔，如: 月考,期中,Unit1")

    # ==== 班级隔离 ====
    class_id = Column(BigInteger, default=None, comment="所属班级ID，null=教师私有")
    exam_id = Column(BigInteger, nullable=True, comment="原件所属试卷")
    source_order = Column(SmallInteger().with_variant(MYSQL_SMALLINT(unsigned=True), "mysql"), nullable=True, comment="原件顺序")
    chat_message_id = Column(BigInteger, nullable=True, index=True, comment="会话附件所属消息")

    __table_args__ = (
        Index("idx_user", "user_id"),
        Index("idx_user_type", "user_id", "file_type"),
        Index("idx_user_category", "user_id", "doc_category"),
        Index("idx_user_stage", "user_id", "stage_category"),
        UniqueConstraint("exam_id", "source_order", name="uq_user_document_exam_order"),
        {"mysql_charset": "utf8mb4", "comment": "用户上传文档表"},
    )


# ──────────────────────────────────────────────
# 2.11 反馈模块
# ──────────────────────────────────────────────

class Feedback(Base):
    """用户反馈表"""
    __tablename__ = "feedback"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    type = Column(String(16), nullable=False, comment="类型: bug/suggestion")
    content = Column(Text, nullable=False, comment="反馈内容")
    screenshot_url = Column(String(512), default="", comment="截图 URL")
    created_at = Column(DateTime, server_default=func.now())

    # 扩展
    contact = Column(String(128), default="", comment="联系方式")
    status = Column(String(16), default="pending", comment="pending/processing/resolved")

    __table_args__ = (
        Index("idx_user", "user_id"),
        {"mysql_charset": "utf8mb4", "comment": "用户反馈表"},
    )


# ──────────────────────────────────────────────
# 学习行为日志（Phase 1 新增）
# ──────────────────────────────────────────────

class LearningBehaviorLog(Base):
    """学习行为日志表：记录学生详细学习行为，用于数据分析和RAG检索"""
    __tablename__ = "learning_behavior_log"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    action_type = Column(String(32), nullable=False, comment="行为类型: start_quiz/submit_answer/start_listening/finish_listening/start_reading/finish_reading/translate/watch_video/create_scenario")
    target_type = Column(String(32), default="", comment="目标类型: question/material/scenario/video")
    target_id = Column(BigInteger, default=0, comment="目标ID")
    detail = Column(JSON, default=None, comment="行为详情(JSON): 正确率/得分/用时等")
    session_duration = Column(Integer, default=0, comment="行为持续时长(秒)")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_user_action", "user_id", "action_type"),
        Index("idx_user_created", "user_id", "created_at"),
        Index("idx_target", "target_type", "target_id"),
        {"mysql_charset": "utf8mb4", "comment": "学习行为日志表"},
    )
