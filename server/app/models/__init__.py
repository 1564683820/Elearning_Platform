"""
ORM Model 汇总 — 对齐 DBplan 全部表

导入此模块即可让 SQLAlchemy 注册所有表的 metadata，
Alembic autogenerate 也能检测到。
"""
from app.models.user import User, UserApiKey, UserReminder
from app.models.word import (
    DictWord, DictRoot, DictWordRoot, StageWord, WordSynonym,
    Favorite, UserWordProgress,
)
from app.models.quiz import (
    QuestionBank, ReadingMaterial, ListeningMaterial,
    StudyRecord, TrainingSession, UserQuizLog, WrongQuestion,
)
from app.models.chat import (
    ChatConversation, ChatMessage, ScenarioPassage, Song,
)
from app.models.class_models import Class, ClassStudent, ClassTeacher, ClassStudentInfo
from app.models.stats import UserDailyStat, UserDocument, Feedback, LearningBehaviorLog
from app.models.exam_models import TeacherExam, ExamSubmission, ExamGradingLog, AnswerSheetTemplate
from app.models.membership_models import UserMembershipOrder, RedeemCode
from app.models.textbook_models import TextbookUnit, TextbookPage
from app.models.textbook_upload import TextbookUpload
from app.models.ppt_models import LessonPPT, ClassroomSession
from app.models.mistake_book import MistakeSummaryReport
from app.models.ppt_theme_models import PPTTheme, PptVersion
from app.models.knowledge_graph import KnowledgeGraph
from app.models.video_models import PresetCharacter, AiVideo
from app.models.collaboration_models import AuditLog, SchoolAdmin, LearningReport
from app.models.invite_code import InviteCode
from app.models.teacher_memory import TeacherMemory  # noqa: F401
from app.models.agent_skill import AgentSkill  # noqa: F401
from app.models.teaching_task import TeachingTask, TeachingTaskOutbox  # noqa: F401

__all__ = [
    # 用户模块
    "User", "UserApiKey", "UserReminder",
    # 词典模块
    "DictWord", "DictRoot", "DictWordRoot", "StageWord", "WordSynonym",
    "Favorite", "UserWordProgress",
    # 训练模块
    "QuestionBank", "ReadingMaterial", "ListeningMaterial",
    "StudyRecord", "TrainingSession", "UserQuizLog", "WrongQuestion",
    # 对话模块
    "ChatConversation", "ChatMessage", "ScenarioPassage", "Song",
    # 班级模块
    "Class", "ClassStudent", "ClassTeacher", "ClassStudentInfo",
    # 试卷模块
    "TeacherExam", "ExamSubmission", "ExamGradingLog", "AnswerSheetTemplate",
    # 会员模块
    "UserMembershipOrder", "RedeemCode",
    # 教材点读
    "TextbookUnit", "TextbookPage", "TextbookUpload",
    # AI备课PPT
    "LessonPPT", "ClassroomSession", "PPTTheme", "PptVersion", "KnowledgeGraph",
    # AI视频教材演绎
    "PresetCharacter", "AiVideo",
    # 协作增强
    "AuditLog", "SchoolAdmin", "LearningReport",
    # 邀请码
    "InviteCode",
    # 教师长期记忆
    "TeacherMemory",
    # Agent 自定义技能
    "AgentSkill",
    # 统计/文档/反馈
    "UserDailyStat", "UserDocument", "Feedback", "LearningBehaviorLog",
    # 错题本
    "MistakeSummaryReport",
]
