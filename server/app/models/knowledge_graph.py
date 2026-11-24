"""知识图谱 ORM 模型"""
from sqlalchemy import Column, BigInteger, String, JSON, DateTime, Index, func
from app.db.database import Base
from app.utils.snowflake import next_id


class KnowledgeGraph(Base):
    """知识图谱表：AI 生成的课程知识结构树，支持教师编辑后确认生成 PPT"""
    __tablename__ = "knowledge_graph"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    ppt_id = Column(BigInteger, default=None, comment="关联 PPT ID（生成后填充）")
    teacher_id = Column(BigInteger, nullable=False, comment="教师 ID")
    title = Column(String(256), nullable=False, comment="课程标题")
    lesson_type = Column(String(32), nullable=False, comment="课型")
    subject = Column(String(128), default="", comment="主题/单元")
    grade = Column(String(16), default="", comment="适用年级")
    content = Column(JSON, nullable=False, comment="图谱内容 {sections: [...]}")
    status = Column(String(16), default="draft", comment="状态: draft/confirmed")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_kg_teacher", "teacher_id"),
        Index("idx_kg_ppt", "ppt_id"),
        {"mysql_charset": "utf8mb4", "comment": "知识图谱表"},
    )
