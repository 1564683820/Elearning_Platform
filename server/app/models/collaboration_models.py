# 协作增强模块 ORM 模型
# 审计日志、学校管理员、学习报告
from sqlalchemy import (
    Column, BigInteger, Integer, String, JSON, Date, DateTime, Index, UniqueConstraint, func,
)
from app.db.database import Base
from app.utils.snowflake import next_id


class AuditLog(Base):
    """操作审计日志表 — 记录所有批改/管理操作"""
    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    class_id = Column(BigInteger, default=None, comment="关联班级ID")
    operator_id = Column(BigInteger, nullable=False, comment="操作人用户ID")
    operator_role = Column(String(20), nullable=False, default="teacher", comment="操作人角色: teacher/assistant/admin/system")
    action_type = Column(String(50), nullable=False, comment="操作类型")
    target_type = Column(String(50), default=None, comment="操作对象类型")
    target_id = Column(BigInteger, default=None, comment="操作对象ID")
    detail = Column(JSON, default=None, comment="操作详情 JSON")
    ip_address = Column(String(45), default=None, comment="操作人IP地址")
    created_at = Column(DateTime, server_default=func.now(), comment="操作时间")

    __table_args__ = (
        Index("idx_audit_class", "class_id"),
        Index("idx_audit_operator", "operator_id"),
        Index("idx_audit_action", "action_type"),
        Index("idx_audit_created", "created_at"),
        {"mysql_charset": "utf8mb4", "comment": "操作审计日志表"},
    )


class SchoolAdmin(Base):
    """学校管理员表 — 教育局/学校级别的数据管理"""
    __tablename__ = "school_admin"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, unique=True, comment="管理员用户ID")
    school_name = Column(String(200), nullable=False, comment="学校名称")
    contact_phone = Column(String(20), default=None, comment="联系电话")
    permissions = Column(JSON, default=None, comment="权限配置JSON")
    is_active = Column(Integer, default=1, comment="是否启用")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_school_name", "school_name"),
        Index("idx_school_active", "is_active"),
        {"mysql_charset": "utf8mb4", "comment": "学校管理员表"},
    )


class LearningReport(Base):
    """学习报告缓存表 — 个人/班级/学期报告"""
    __tablename__ = "learning_report"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="学生用户ID")
    class_id = Column(BigInteger, default=None, comment="所属班级ID")
    report_type = Column(String(20), nullable=False, default="personal", comment="报告类型: personal/class/semester")
    period_start = Column(Date, nullable=False, comment="统计开始日期")
    period_end = Column(Date, nullable=False, comment="统计结束日期")
    report_data = Column(JSON, nullable=False, comment="报告数据JSON")
    generated_at = Column(DateTime, server_default=func.now(), comment="生成时间")

    __table_args__ = (
        Index("idx_report_user_class", "user_id", "class_id"),
        Index("idx_report_type", "report_type"),
        Index("idx_report_generated", "generated_at"),
        {"mysql_charset": "utf8mb4", "comment": "学习报告缓存表"},
    )
