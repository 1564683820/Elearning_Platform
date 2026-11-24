# 试卷模块 ORM 模型
# 包含试卷主表、学生提交表、批改日志表
from sqlalchemy import (
    Column, BigInteger, SmallInteger, Integer, String, Text, JSON,
    DateTime, Index, UniqueConstraint, Computed, func,
)
from sqlalchemy.dialects.mysql import INTEGER as MYSQL_INTEGER
from app.db.database import Base
from app.utils.snowflake import next_id


class TeacherExam(Base):
    """试卷主表：教师创建的试卷，含题目 JSON"""
    __tablename__ = "teacher_exam"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    teacher_id = Column(BigInteger, nullable=False, comment="创建教师ID")
    class_id = Column(BigInteger, nullable=False, comment="目标班级ID")
    title = Column(String(256), nullable=False, comment="试卷标题")
    description = Column(String(512), default="", comment="试卷描述")
    questions = Column(JSON, nullable=False, comment="题目列表 JSON")
    total_score = Column(Integer, default=100, comment="总分")
    difficulty = Column(SmallInteger, default=1, comment="难度: 1=简单,2=中等,3=困难")
    duration_minutes = Column(Integer, default=60, comment="建议用时(分钟)")
    knowledge_points = Column(String(512), default="", comment="知识点标签,逗号分隔")
    grade = Column(String(16), default="", comment="适用年级，如：五年级、七年级")
    submission_count = Column(Integer, default=0, comment="提交人数")
    avg_score = Column(Integer, default=None, comment="平均分")
    status = Column(String(16), default="draft", comment="状态: draft/published/grading/done/archived")
    published_at = Column(DateTime, default=None, comment="发布时间")
    done_at = Column(DateTime, default=None, comment="批改完成时间")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # ==== 学段 & 组卷来源 ====
    stage_category = Column(String(16), default="other",
        comment="学段: preschool/primary/junior/senior/other")
    source_exam_ids = Column(String(255), default="",
        comment="组卷来源试卷ID列表，逗号分隔")

    # ==== 答题卡配置（发布时自动生成） ====
    answer_sheet_config = Column(JSON, default=None,
        comment="答题卡配置: {total_questions, option_count, options, regions, coordinate_config, html_url, pdf_url}")

    __table_args__ = (
        Index("idx_exam_teacher", "teacher_id"),
        Index("idx_exam_class", "class_id"),
        Index("idx_exam_status", "status"),
        Index("idx_exam_stage", "stage_category"),
        {"mysql_charset": "utf8mb4", "comment": "试卷主表"},
    )


class ExamSubmission(Base):
    """学生提交表：学生作答 + AI 评分结果"""
    __tablename__ = "exam_submission"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    exam_id = Column(BigInteger, nullable=False, comment="试卷ID")
    student_id = Column(BigInteger, nullable=True, default=None, comment="学生ID（扫描批卷未识别考号时可为NULL）")
    answers = Column(JSON, nullable=False, comment="学生答案 JSON")
    score = Column(Integer, default=None, comment="AI 评分总得分")
    max_score = Column(Integer, default=None, comment="满分")
    ai_grade_detail = Column(JSON, default=None, comment="AI 逐题评分详情")
    teacher_adjustment = Column(JSON, default=None, comment="教师调整记录")
    adjusted_score = Column(Integer, default=None, comment="教师调整后分数")
    exam_number = Column(String(64), default="", comment="考号/学号（OCR批卷匹配用）")
    started_at = Column(DateTime, default=None, comment="开始作答时间")
    submitted_at = Column(DateTime, default=None, comment="提交时间")
    duration_seconds = Column(Integer, default=0, comment="作答用时(秒)")
    grading_status = Column(String(32), default="pending", comment="批改状态: pending/ai_done/teacher_reviewed/omr_*")
    # ====== 扫描批卷扩展字段 ======
    scan_image_url = Column(String(512), default="", comment="扫描答题卡图片URL（OMR批卷来源）")
    scan_record_id = Column(BigInteger, default=0, comment="关联的扫描记录ID")
    wrong_count = Column(Integer, default=0, comment="错题数量")
    grade_version = Column(Integer().with_variant(MYSQL_INTEGER(unsigned=True), "mysql"),
                           nullable=False, server_default="0", comment="固定卡成绩版本")
    unmatched_exam_number = Column(String(64), Computed(
        "CASE WHEN student_id IS NULL AND grade_version > 0 THEN NULLIF(TRIM(exam_number), '') ELSE NULL END",
        persisted=False,
    ))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", name="uk_exam_student"),
        UniqueConstraint("exam_id", "unmatched_exam_number", name="uq_exam_unmatched_number"),
        Index("idx_sub_exam", "exam_id"),
        Index("idx_sub_student", "student_id"),
        {"mysql_charset": "utf8mb4", "comment": "学生提交表"},
    )


class ExamGradingLog(Base):
    """批改日志表：记录所有批改操作（AI 和人工），用于审计和多人协作"""
    __tablename__ = "exam_grading_log"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    submission_id = Column(BigInteger, nullable=False, comment="提交记录ID")
    grader_type = Column(String(16), nullable=False, comment="批改者类型: ai/teacher/assistant")
    grader_id = Column(BigInteger, default=0, comment="批改者用户ID(教师/助教)")
    action = Column(String(32), nullable=False, comment="操作: auto_grade/teacher_review/teacher_adjust")
    detail = Column(JSON, default=None, comment="操作详情 JSON")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_log_submission", "submission_id"),
        Index("idx_log_grader", "grader_id"),
        {"mysql_charset": "utf8mb4", "comment": "批改日志表"},
    )


class AnswerSheetTemplate(Base):
    """答题卡模板表：教师保存的通用答题卡配置模板，可复用于创建试卷"""
    __tablename__ = "answer_sheet_template"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    teacher_id = Column(BigInteger, nullable=False, comment="创建教师ID")
    name = Column(String(128), nullable=False, comment="模板名称")
    grade = Column(String(16), default="", comment="适用年级")
    description = Column(String(512), default="", comment="模板描述")
    choice_questions = Column(JSON, nullable=False, comment="选择题配置JSON（SKILL.md格式）")
    question_count = Column(Integer, default=0, comment="总题数")
    total_score = Column(Integer, default=0, comment="总分")
    is_default = Column(SmallInteger, default=0, comment="是否默认模板: 0=否,1=是")
    archived_at = Column(DateTime, nullable=True, comment="模板停用时间")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_as_template_teacher", "teacher_id"),
        {"mysql_charset": "utf8mb4", "comment": "答题卡模板表"},
    )
