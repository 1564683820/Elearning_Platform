# 扫描批卷模块 ORM 模型
# 包含错题本、扫描记录表
from sqlalchemy import (
    Column, BigInteger, SmallInteger, Integer, String, Text, JSON,
    DateTime, Index, UniqueConstraint, func,
)
from app.db.database import Base
from app.utils.snowflake import next_id


class WrongQuestionBook(Base):
    """错题本表：每道错题一条记录，供RAG教学助手检索"""
    __tablename__ = "wrong_question_book"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    student_id = Column(BigInteger, nullable=False, comment="学生用户ID")
    class_id = Column(BigInteger, nullable=False, comment="班级ID")
    exam_id = Column(BigInteger, nullable=False, comment="试卷ID")
    submission_id = Column(BigInteger, nullable=False, comment="提交记录ID")
    question_index = Column(Integer, nullable=False, comment="题目序号（从1开始）")
    question_type = Column(String(32), default="", comment="题型: single/multiple/fill/reading等")
    question_stem = Column(Text, default="", comment="题干")
    correct_answer = Column(String(512), default="", comment="正确答案")
    student_answer = Column(String(512), default="", comment="学生填涂的答案")
    knowledge_point = Column(String(256), default="", comment="知识点标签")
    score = Column(Integer, default=0, comment="本题得分")
    max_score = Column(Integer, default=0, comment="本题满分")
    error_category = Column(String(32), default="", comment="错误分类: knowledge_gap/careless/misunderstanding/other")
    ai_comment = Column(Text, default="", comment="AI批改评语")
    rag_indexed = Column(SmallInteger, default=0, comment="是否已RAG入库: 0=否,1=是")
    rag_chunk_id = Column(String(64), default="", comment="RAG知识库中的chunk_id")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_wq_student", "student_id"),
        Index("idx_wq_class", "class_id"),
        Index("idx_wq_exam", "exam_id"),
        Index("idx_wq_knowledge", "knowledge_point"),
        Index("idx_wq_rag", "rag_indexed"),
        UniqueConstraint("submission_id", "question_index", name="uk_wq_sub_qidx"),
        {"mysql_charset": "utf8mb4", "comment": "错题本：每道错题一条记录，供RAG教学助手检索"},
    )


class ExamScanRecord(Base):
    """扫描批卷记录表：记录每次扫描的元信息，用于追溯和调试"""
    __tablename__ = "exam_scan_record"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    exam_id = Column(BigInteger, nullable=False, comment="试卷ID")
    teacher_id = Column(BigInteger, nullable=False, comment="操作教师ID")
    scan_image_url = Column(String(512), default="", comment="上传的答题卡图片URL")
    recognized_count = Column(Integer, default=0, comment="识别到的答题数")
    matched_student_id = Column(BigInteger, default=0, comment="匹配到的学生ID（考号匹配）")
    exam_number = Column(String(64), default="", comment="识别到的考号")
    raw_answers = Column(JSON, default=None, comment="OMR识别的原始答案")
    grading_result = Column(JSON, default=None, comment="批改结果摘要")
    scan_duration_ms = Column(Integer, default=0, comment="扫描处理耗时(毫秒)")
    error_message = Column(Text, default="", comment="错误信息（如有）")
    created_at = Column(DateTime, server_default=func.now())
    request_id = Column(String(64), nullable=True, comment="固定卡识别请求标识")
    status = Column(String(16), nullable=True, comment="固定卡扫描处理状态")
    updated_at = Column(DateTime, nullable=True, onupdate=func.now(), comment="固定卡扫描最后处理时间")

    __table_args__ = (
        Index("idx_esr_exam", "exam_id"),
        Index("idx_esr_teacher", "teacher_id"),
        Index("idx_esr_student", "matched_student_id"),
        Index("ix_scan_exam_updated", "exam_id", "updated_at", "id"),
        UniqueConstraint("exam_id", "teacher_id", "request_id", name="uq_scan_exam_request"),
        {"mysql_charset": "utf8mb4", "comment": "扫描批卷记录表"},
    )
