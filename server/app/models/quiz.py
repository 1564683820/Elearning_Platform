"""
训练模块 Model — 对齐 DBplan 2.4 / 2.5

表清单:
  question_bank      题库表
  reading_material   阅读材料表
  listening_material 听力材料表（DBplan 扩展）
  training_session   训练会话表
  user_quiz_log      答题记录表
  wrong_question     错题表
  study_record       学习记录表
"""
from sqlalchemy import (
    Column, BigInteger, Integer, SmallInteger, String, Text, JSON, DateTime,
    Index, UniqueConstraint, func,
)
from app.db.database import Base
from app.utils.snowflake import next_id


# ──────────────────────────────────────────────
# 2.4 训练模块
# ──────────────────────────────────────────────

class QuestionBank(Base):
    """题库表"""
    __tablename__ = "question_bank"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    stage = Column(SmallInteger, nullable=False, comment="适用学习阶段: 1=小学,2=初中,3=高中,4=四六级")
    type = Column(SmallInteger, nullable=False, comment="题型: 1=选择填空,2=选择翻译,3=听力选择,4=短语语法,5=句子翻译,6=阅读理解,7=听力训练,8=句子翻译(填空),9=作文写作")
    difficulty = Column(SmallInteger, default=1, comment="难度 1-3")
    content = Column(JSON, nullable=False, comment="题目内容(题干/选项/答案/解析)")
    source = Column(String(128), default="", comment="来源(试卷名/教材/AI生成)")
    audio_url = Column(String(512), default="", comment="听力题音频 URL")
    reading_id = Column(BigInteger, default=None, comment="关联阅读材料 ID")
    word_id = Column(Integer, default=None, comment="关联单词 ID")
    created_at = Column(DateTime, server_default=func.now())

    # 扩展
    is_active = Column(SmallInteger, default=1, comment="是否启用 0/1")

    __table_args__ = (
        Index("idx_stage_type", "stage", "type"),
        Index("idx_word_id", "word_id"),
        {"mysql_charset": "utf8mb4", "comment": "题库表"},
    )


class ReadingMaterial(Base):
    """阅读材料表"""
    __tablename__ = "reading_material"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    stage = Column(SmallInteger, nullable=False, comment="学习阶段: 1=小学,2=初中,3=高中,4=四六级")
    title = Column(String(256), nullable=False, comment="标题")
    content = Column(Text, nullable=False, comment="英文正文")
    content_cn = Column(Text, comment="中文翻译")
    type = Column(String(16), default="article", comment="素材类型: article/story/news")
    source = Column(String(256), default="", comment="来源")

    # 扩展
    word_count = Column(Integer, default=0, comment="字数")
    difficulty = Column(SmallInteger, default=1, comment="难度 1-5")
    audio_url = Column(String(512), default="", comment="配套音频 URL")

    __table_args__ = (
        Index("idx_stage_type", "stage", "type"),
        {"mysql_charset": "utf8mb4", "comment": "阅读材料表"},
    )


class ListeningMaterial(Base):
    """听力材料表（DBplan 扩展）"""
    __tablename__ = "listening_material"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    stage = Column(SmallInteger, nullable=False, comment="学习阶段: 1=小学,2=初中,3=高中,4=四六级")
    title = Column(String(256), nullable=False, comment="标题")
    audio_url = Column(String(512), nullable=False, comment="音频 URL")
    transcript = Column(Text, comment="听力原文")
    transcript_cn = Column(Text, comment="中文翻译")
    duration = Column(Integer, default=0, comment="时长(秒)")
    type = Column(String(16), default="article", comment="类型: article/story/news")
    source = Column(String(128), default="", comment="来源")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_stage_type", "stage", "type"),
        {"mysql_charset": "utf8mb4", "comment": "听力材料表"},
    )


# ──────────────────────────────────────────────
# 2.5 学习记录模块
# ──────────────────────────────────────────────

class StudyRecord(Base):
    """学习记录表"""
    __tablename__ = "study_record"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    word_id = Column(Integer, nullable=False, comment="单词ID(dict_word.id)")
    action = Column(SmallInteger, nullable=False, comment="动作: 1=浏览,2=收藏,3=取消收藏,4=发音播放")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_user_word", "user_id", "word_id"),
        Index("idx_user_created", "user_id", "created_at"),
        {"mysql_charset": "utf8mb4", "comment": "学习记录表"},
    )


class TrainingSession(Base):
    """训练会话表"""
    __tablename__ = "training_session"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    type = Column(SmallInteger, nullable=False, comment="训练类型(同 question_bank.type)")
    total_count = Column(Integer, nullable=False, comment="总题数")
    correct_count = Column(Integer, default=0, comment="正确数")
    duration_sec = Column(Integer, default=0, comment="用时(秒)")
    finished_at = Column(DateTime, default=None, comment="完成时间")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_user_created", "user_id", "created_at"),
        {"mysql_charset": "utf8mb4", "comment": "训练会话表"},
    )


class UserQuizLog(Base):
    """答题记录表（每道题维度）"""
    __tablename__ = "user_quiz_log"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    session_id = Column(BigInteger, default=None, comment="训练会话ID(training_session.id)")
    question_id = Column(BigInteger, nullable=False, comment="题目ID")
    question_type = Column(SmallInteger, nullable=False, comment="题型")
    is_correct = Column(SmallInteger, nullable=False, comment="0错/1对")
    user_answer = Column(JSON, default=None, comment="用户答案")
    time_spent = Column(Integer, default=0, comment="用时(秒)")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_user_session", "user_id", "session_id"),
        Index("idx_question", "question_id"),
        {"mysql_charset": "utf8mb4", "comment": "答题记录表"},
    )


class WrongQuestion(Base):
    """错题表：记录学生答错的题目，支持分类和知识点标记"""
    __tablename__ = "wrong_question"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    question_id = Column(BigInteger, nullable=False, comment="题目ID")
    question_type = Column(SmallInteger, nullable=False, comment="题型: 1=单词,2=语法")
    # 扩展字段：错题分类和知识点标记
    category = Column(String(64), default="", comment="错题分类: vocabulary/grammar/reading/listening/translation")
    knowledge_point = Column(String(256), default="", comment="涉及知识点标签，逗号分隔")
    # 班级隔离
    class_id = Column(BigInteger, default=None, comment="所属班级ID，null=全局错题")
    related_word_id = Column(Integer, default=None, comment="关联单词ID(dict_word.id)")
    wrong_count = Column(Integer, default=1, comment="错误次数")
    last_wrong_at = Column(DateTime, nullable=False, comment="最近错误时间")
    mastered = Column(SmallInteger, default=0, comment="是否已掌握 0/1")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uk_user_question"),
        Index("idx_user_type_mastered", "user_id", "question_type", "mastered"),
        Index("idx_category", "user_id", "category"),
        {"mysql_charset": "utf8mb4", "comment": "错题表"},
    )
