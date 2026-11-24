"""
智能对话 + 情景记忆 + 歌曲推荐 Model — 对齐 DBplan 2.7 / 2.8 / 2.9

表清单:
  chat_conversation  对话会话表
  chat_message       对话消息表
  scenario_passage   情景文段表
  song               推荐歌曲表
"""
from sqlalchemy import (
    Column, BigInteger, Integer, SmallInteger, String, Text, JSON, Date, DateTime,
    Index, UniqueConstraint, func,
)
from app.db.database import Base
from app.utils.snowflake import next_id


# ──────────────────────────────────────────────
# 2.7 智能对话模块
# ──────────────────────────────────────────────

class ChatConversation(Base):
    """对话会话表"""
    __tablename__ = "chat_conversation"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    type = Column(SmallInteger, nullable=False, comment="1=情景对话,2=智能问答,3=智能翻译,4=教学助手")
    scene_desc = Column(String(512), default="", comment="场景描述(情景对话)")
    user_role = Column(String(128), default="", comment="用户身份(情景对话)")
    evaluation = Column(JSON, default=None, comment="AI 评价结果")
    created_at = Column(DateTime, server_default=func.now())

    # 扩展
    title = Column(String(256), default="", comment="会话标题")
    summary = Column(Text, default="", comment="对话摘要（LLM自动生成）")
    class_id = Column(BigInteger, default=None, comment="关联班级ID")
    status = Column(SmallInteger, default=1, comment="1=活跃 0=已归档")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_user_type", "user_id", "type"),
        Index("idx_chat_teacher_type", "user_id", "type", "status"),
        {"mysql_charset": "utf8mb4", "comment": "对话会话表"},
    )


class ChatMessage(Base):
    """对话消息表"""
    __tablename__ = "chat_message"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    conversation_id = Column(BigInteger, nullable=False, index=True, comment="会话ID")
    role = Column(String(16), nullable=False, comment="user/assistant/system")
    content = Column(Text, nullable=False, comment="消息内容")
    sources = Column(JSON, default=None, comment="引用来源(智能问答返回的链接列表)")
    created_at = Column(DateTime, server_default=func.now())

    # 扩展
    message_type = Column(String(32), default="text", comment="text/image/file")
    request_id = Column(String(64), nullable=True, comment="教学助手提问重试标识")
    reply_to_message_id = Column(BigInteger, nullable=True, comment="教学助手回复对应的提问")

    __table_args__ = (
        UniqueConstraint("conversation_id", "request_id", name="uq_chat_message_request"),
        UniqueConstraint("reply_to_message_id", name="uq_chat_message_reply"),
        {"mysql_charset": "utf8mb4", "comment": "对话消息表"},
    )


# ──────────────────────────────────────────────
# 2.8 情景记忆模块
# ──────────────────────────────────────────────

class ScenarioPassage(Base):
    """情景文段表"""
    __tablename__ = "scenario_passage"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    word_ids = Column(JSON, nullable=False, comment="涉及的错题单词 ID 列表")
    passage_type = Column(String(16), nullable=False, comment="文段类型: report/story/rhyme")
    content = Column(Text, nullable=False, comment="文段内容(单词高亮标记)")
    video_url = Column(String(512), default="", comment="生成的视频 URL")
    video_status = Column(SmallInteger, default=0, comment="视频状态: 0=未生成,1=生成中,2=已完成,3=失败")
    expires_at = Column(DateTime, nullable=False, comment="过期时间(30天)")
    created_at = Column(DateTime, server_default=func.now())

    # 扩展
    model_used = Column(String(128), default="", comment="使用的模型")

    __table_args__ = (
        Index("idx_user_expires", "user_id", "expires_at"),
        {"mysql_charset": "utf8mb4", "comment": "情景文段表"},
    )


# ──────────────────────────────────────────────
# 2.9 歌曲推荐模块
# ──────────────────────────────────────────────

class Song(Base):
    """推荐歌曲表"""
    __tablename__ = "song"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(128), nullable=False, comment="歌名")
    artist = Column(String(128), nullable=False, comment="歌手")
    cover_url = Column(String(512), default="", comment="封面图 URL")
    lyrics_en = Column(Text, comment="英文歌词")
    lyrics_cn = Column(Text, comment="中文歌词")
    audio_url = Column(String(512), default="", comment="音频 URL")
    stage = Column(SmallInteger, default=0, comment="适合阶段(0=全阶段)")
    recommend_date = Column(Date, nullable=False, comment="推荐日期")

    __table_args__ = (
        Index("idx_date", "recommend_date"),
        {"mysql_charset": "utf8mb4", "comment": "推荐歌曲表"},
    )
