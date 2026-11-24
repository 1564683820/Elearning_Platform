"""Persistent teaching workflow state, owned by one teacher and class."""
from sqlalchemy import Column, BigInteger, Integer, String, Text, JSON, DateTime, Index, func
from app.db.database import Base
from app.utils.snowflake import next_id


class TeachingTask(Base):
    __tablename__ = 'teaching_task'

    id = Column(BigInteger, primary_key=True, default=next_id, autoincrement=False)
    teacher_id = Column(BigInteger, nullable=False)
    class_id = Column(BigInteger, nullable=False)
    objective = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default='created')
    checkpoint = Column(JSON, nullable=False, default=dict)
    artifact = Column(JSON, nullable=False, default=dict)
    artifact_version = Column(Integer, nullable=False, default=0)
    approved_version = Column(Integer, nullable=True)
    published_exam_id = Column(BigInteger, nullable=True, unique=True)
    error_code = Column(String(64), nullable=True)
    lease_owner = Column(String(64), nullable=True)
    lease_until = Column(DateTime, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (Index('idx_teaching_task_owner', 'teacher_id', 'created_at'),)


class TeachingTaskOutbox(Base):
    """Task and dispatch intent commit in the same SQL transaction."""
    __tablename__ = 'teaching_task_outbox'
    id = Column(BigInteger, primary_key=True, default=next_id, autoincrement=False)
    task_id = Column(BigInteger, nullable=False, index=True)
    delivered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
