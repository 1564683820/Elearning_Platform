# 班级模块 ORM 模型
# 包含班级、班级-学生关联、班级-教师关联三个模型
from sqlalchemy import (
    Column, BigInteger, SmallInteger, Integer, String, DateTime,
    Index, UniqueConstraint, func,
)
from app.db.database import Base
from app.utils.snowflake import next_id


class ClassStudentInfo(Base):
    """学生信息表：通过 Excel 导入的学生花名册，用于 OCR 批卷时匹配成绩"""
    __tablename__ = "class_student_info"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    class_id = Column(BigInteger, nullable=False, comment="班级ID")
    student_number = Column(Integer, nullable=False, comment="学生序号")
    student_name = Column(String(64), nullable=False, comment="学生姓名")
    exam_number = Column(String(64), nullable=False, comment="考号/学号")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    __table_args__ = (
        Index("idx_csi_class", "class_id"),
        UniqueConstraint("class_id", "exam_number", name="uk_csi_class_exam"),
        {"mysql_charset": "utf8mb4", "comment": "班级学生信息表(Excel导入)"},
    )


class Class(Base):
    """班级表：由教师创建，每个班级有唯一邀请码"""
    __tablename__ = "class"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    name = Column(String(128), nullable=False, comment="班级名称")
    description = Column(String(512), default="", comment="班级描述")
    invite_code = Column(String(32), nullable=False, unique=True, comment="邀请码(唯一)")
    created_by = Column(BigInteger, nullable=False, comment="创建者教师ID")
    stage = Column(SmallInteger, default=0, comment="默认学习阶段")
    student_count = Column(Integer, default=0, comment="学生人数(冗余)")
    is_active = Column(SmallInteger, default=1, comment="是否启用 0/1")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_created_by", "created_by"),
        Index("idx_stage", "stage"),
        {"mysql_charset": "utf8mb4", "comment": "班级表"},
    )


class ClassStudent(Base):
    """班级-学生关联表：记录学生加入班级信息"""
    __tablename__ = "class_student"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    class_id = Column(BigInteger, nullable=False, comment="班级ID")
    student_id = Column(BigInteger, nullable=False, comment="学生ID")
    joined_at = Column(DateTime, server_default=func.now(), comment="加入时间")

    __table_args__ = (
        UniqueConstraint("class_id", "student_id", name="uk_class_student"),
        Index("idx_student", "student_id"),
        {"mysql_charset": "utf8mb4", "comment": "班级-学生关联表"},
    )


class ClassTeacher(Base):
    """班级-教师关联表：支持多教师和助教角色"""
    __tablename__ = "class_teacher"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    class_id = Column(BigInteger, nullable=False, comment="班级ID")
    teacher_id = Column(BigInteger, nullable=False, comment="教师ID")
    role = Column(String(16), nullable=False, default="teacher", comment="角色: teacher/assistant")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("class_id", "teacher_id", name="uk_class_teacher"),
        Index("idx_teacher", "teacher_id"),
        {"mysql_charset": "utf8mb4", "comment": "班级-教师关联表"},
    )
