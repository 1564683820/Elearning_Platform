"""邀请码 Model — 用于学生/教师通过邀请码自助注册"""
from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, String, DateTime, SmallInteger,
    func,
)
from app.db.database import Base
from app.utils.snowflake import next_id


class InviteCode(Base):
    """邀请码表：管理员生成，注册时验证"""
    __tablename__ = "invite_code"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    code = Column(String(32), unique=True, nullable=False, index=True, comment="邀请码")
    role = Column(String(16), nullable=False, default="student", comment="邀请码角色: student/teacher")
    is_used = Column(SmallInteger, default=0, comment="0=未使用, 1=已使用")
    used_by = Column(BigInteger, default=None, comment="使用者用户ID")
    used_at = Column(DateTime, default=None, comment="使用时间")
    created_by = Column(BigInteger, nullable=False, comment="创建人ID（管理员）")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    is_deleted = Column(SmallInteger, default=0, comment="0=正常, 1=已删除")
    deleted_at = Column(DateTime, default=None, comment="删除时间")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "comment": "邀请码表"},
    )
