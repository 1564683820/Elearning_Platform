"""Agent 自定义技能模型 — 教师上传 SKILL.md 自定义小e的PPT/试卷生成风格"""

from sqlalchemy import (
    Column, BigInteger, String, Text, JSON, DateTime, SmallInteger, Index, func,
)
from app.db.database import Base
from app.utils.snowflake import next_id


class AgentSkill(Base):
    """教师自定义Agent技能表 — 每行对应一个上传的 SKILL.md

    技能按类型分类: ppt (PPT课件设计), exam (试卷设计)
    每个教师每类技能可激活一个，不同类型的技能互不影响。
    """

    __tablename__ = "agent_skill"

    id = Column(BigInteger, primary_key=True, autoincrement=False, default=next_id)
    teacher_id = Column(BigInteger, nullable=False, comment="所属教师ID")
    skill_type = Column(String(32), default="ppt", comment="技能类型: ppt=PPT设计, exam=试卷设计")
    name = Column(String(128), nullable=False, comment="技能名称（取自 SKILL.md frontmatter name）")
    source_filename = Column(String(256), nullable=True, comment="上传的原始 Markdown 文件名")
    description = Column(Text, default="", comment="技能描述（取自 SKILL.md frontmatter description）")
    raw_content = Column(Text, nullable=False, comment="原始 SKILL.md 完整内容")
    # 解析后的设计令牌
    design_tokens = Column(JSON, default=None, comment="解析后的设计令牌: {colors, typography, spacing, rounded, components}")
    # 缩减后的系统提示词（用于注入到 Agent prompt 中，控制token消耗）
    prompt_snippet = Column(Text, default="", comment="用于注入Agent系统提示词的压缩版设计规范")
    is_active = Column(SmallInteger, default=0, comment="是否当前激活: 1=是,0=否（同一教师每类技能可激活一个）")
    status = Column(SmallInteger, default=1, comment="状态: 1=正常,0=已删除")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_askill_teacher", "teacher_id"),
        Index("idx_askill_teacher_type", "teacher_id", "skill_type"),
        Index("idx_askill_active", "teacher_id", "skill_type", "is_active"),
        {"mysql_charset": "utf8mb4", "comment": "Agent自定义技能表"},
    )
