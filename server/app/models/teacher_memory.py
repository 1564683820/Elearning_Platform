"""
教师长期记忆表 — 记录教师教学偏好、话题总结、班级观察等长期记忆
"""

from sqlalchemy import Column, BigInteger, String, Text, JSON, Float, Integer, DateTime, Index, func
from app.db.database import Base
from app.utils.snowflake import next_id


class TeacherMemory(Base):
    """教师长期记忆表"""
    __tablename__ = "teacher_memory"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    teacher_id = Column(BigInteger, nullable=False, comment="教师ID")
    memory_type = Column(String(32), nullable=False, comment="preference/topic_summary/class_note/teaching_style")
    memory_key = Column(String(128), nullable=False, comment="记忆键")
    memory_value = Column(Text, nullable=False, comment="记忆值")
    importance = Column(Float, default=0.5, comment="重要性 0-1")
    trigger_keywords = Column(JSON, default=None, comment="触发关键词列表")
    access_count = Column(Integer, default=0, comment="被引用次数")
    last_accessed_at = Column(DateTime, default=None, comment="最后访问时间")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_tm_teacher_type", "teacher_id", "memory_type"),
        Index("idx_tm_teacher_key", "teacher_id", "memory_key"),
        {"mysql_charset": "utf8mb4", "comment": "教师长期记忆表"},
    )
