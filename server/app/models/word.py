"""
词典模块 Model — 对齐 DBplan 2.2 / 2.3 / 2.6

表清单:
  dict_word      词典主表（ECDICT 导入）
  dict_root      词根词缀表
  dict_word_root 单词-词根关联表
  stage_word     学习阶段-单词映射表
  word_synonym   近义词表（DBplan 扩展）
  favorite       收藏表
  user_word_progress 用户单词进度表
"""
from sqlalchemy import (
    Column, BigInteger, Integer, SmallInteger, String, Text, JSON, DateTime,
    Index, UniqueConstraint, func,
)
from app.db.database import Base, WordBase
from app.utils.snowflake import next_id


# ──────────────────────────────────────────────
# 2.2 词典模块（单词专用库 elearnword）
# ──────────────────────────────────────────────

class DictWord(WordBase):
    """词典主表 — 从 ECDICT 导入"""
    __tablename__ = "dict_word"

    id = Column(Integer, primary_key=True, autoincrement=True)
    word = Column(String(128), unique=True, nullable=False, comment="单词")
    sw = Column(String(128), nullable=False, index=True, comment="模糊匹配键")
    phonetic = Column(String(128), default="", comment="音标")
    definition = Column(Text, comment="英文释义")
    translation = Column(Text, comment="中文释义")
    pos = Column(String(128), default="", comment="词性占比, 如 n:46/v:54")
    collins = Column(SmallInteger, default=0, comment="柯林斯星级 1-5")
    oxford = Column(SmallInteger, default=0, comment="牛津三千核心词 0/1")
    tag = Column(String(256), default="", comment="考试标签, 如 cet4 zk gk")
    bnc = Column(Integer, default=0, comment="英国国家语料库词频排名")
    frq = Column(Integer, default=0, comment="当代语料库词频排名")
    exchange = Column(String(256), default="", comment="词形变化, 如 d:perceived/p:perceived")
    audio_url = Column(String(512), default="", comment="发音音频 URL")

    # 扩展字段（DBplan 之外的实用补充）
    detail_json = Column(JSON, default=None, comment="扩展信息（词根、近义词、记忆金句等）")

    __table_args__ = (
        Index("idx_sw", "sw"),
        Index("idx_tag", "tag", mysql_length=64),
        Index("idx_collins", "collins"),
        {"mysql_charset": "utf8mb4", "comment": "词典主表(ECDICT)"},
    )


class DictRoot(WordBase):
    """词根词缀表"""
    __tablename__ = "dict_root"

    id = Column(Integer, primary_key=True, autoincrement=True)
    root = Column(String(64), nullable=False, index=True, comment="词根/词缀")
    root_type = Column(String(16), nullable=False, comment="prefix/root/suffix")
    meaning = Column(String(256), default="", comment="含义")
    origin = Column(String(64), default="", comment="语源(拉丁/希腊等)")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "comment": "词根词缀表"},
    )


class DictWordRoot(WordBase):
    """单词与词根关联表"""
    __tablename__ = "dict_word_root"

    id = Column(Integer, primary_key=True, autoincrement=True)
    word_id = Column(Integer, nullable=False, index=True, comment="关联 dict_word.id")
    root_id = Column(Integer, nullable=False, index=True, comment="关联 dict_root.id")
    position = Column(SmallInteger, default=0, comment="在单词中的位置顺序")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "comment": "单词-词根关联表"},
    )


# ──────────────────────────────────────────────
# 2.3 学习阶段与单词映射
# ──────────────────────────────────────────────

class StageWord(WordBase):
    """学习阶段-单词映射表"""
    __tablename__ = "stage_word"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    word_id = Column(Integer, nullable=False, comment="关联 dict_word.id")
    stage = Column(SmallInteger, nullable=False, comment="学习阶段: 1=小学,2=初中,3=高中,4=四六级")
    mastery_order = Column(Integer, default=0, comment="同阶段内掌握顺序")

    __table_args__ = (
        UniqueConstraint("word_id", "stage", name="uk_word_stage"),
        Index("idx_stage_order", "stage", "mastery_order"),
        {"mysql_charset": "utf8mb4", "comment": "阶段-单词映射表"},
    )


# ──────────────────────────────────────────────
# 扩展表（DBplan 之外的实用补充）
# ──────────────────────────────────────────────

class WordSynonym(WordBase):
    """近义词辨析表"""
    __tablename__ = "word_synonyms"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    word_id = Column(BigInteger, nullable=False, index=True, comment="单词ID")
    synonym_word = Column(String(128), nullable=False, comment="近义词")
    tag = Column(String(64), default="", comment="辨析标签")
    usage_desc = Column(Text, comment="用法说明")
    example = Column(Text, comment="辨析例句")

    __table_args__ = (
        {"mysql_charset": "utf8mb4", "comment": "近义词辨析表"},
    )


# ──────────────────────────────────────────────
# 2.6 收藏模块
# ──────────────────────────────────────────────

class Favorite(Base):
    """收藏表"""
    __tablename__ = "favorite"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    target_type = Column(SmallInteger, nullable=False, comment="1=单词,2=文章,3=情景文段,4=歌曲")
    target_id = Column(BigInteger, nullable=False, comment="目标ID")
    word = Column(String(255), default="", comment="单词文本（单词收藏）")
    phonetic = Column(String(255), default="", comment="音标（单词收藏）")
    meaning = Column(String(1024), default="", comment="释义（单词收藏）")
    content = Column(Text, default="", comment="文段内容（情景文段收藏）")
    passage_type = Column(String(50), default="", comment="文段类型（情景文段收藏）")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "target_type", "target_id", name="uk_user_target"),
        Index("idx_user_type", "user_id", "target_type"),
        {"mysql_charset": "utf8mb4", "comment": "收藏表"},
    )


# ──────────────────────────────────────────────
# 学习进度
# ──────────────────────────────────────────────

class UserWordProgress(WordBase):
    """用户单词学习进度"""
    __tablename__ = "user_word_progress"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    word_id = Column(Integer, nullable=False, comment="单词ID(dict_word.id)")
    mastery_level = Column(SmallInteger, default=0, comment="0未学/1认识/2熟悉/3掌握")
    review_count = Column(Integer, default=0, comment="复习次数")
    last_reviewed_at = Column(DateTime, default=None, comment="最后复习时间")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "word_id", name="uk_user_word"),
        Index("idx_user_mastery", "user_id", "mastery_level"),
        {"mysql_charset": "utf8mb4", "comment": "用户单词学习进度"},
    )
