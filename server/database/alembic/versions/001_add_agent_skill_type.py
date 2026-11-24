"""Add skill_type column to agent_skill table

Revision ID: 001
Revises: None
Create Date: 2026-06-29 23:23:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_skill",
        sa.Column(
            "skill_type",
            sa.String(32),
            server_default="ppt",
            nullable=False,
            comment="技能类型: ppt=PPT设计, exam=试卷设计",
        ),
    )
    op.create_index("idx_askill_teacher_type", "agent_skill", ["teacher_id", "skill_type"])
    op.create_index("idx_askill_active", "agent_skill", ["teacher_id", "skill_type", "is_active"])


def downgrade() -> None:
    op.drop_index("idx_askill_teacher_type", table_name="agent_skill")
    op.drop_index("idx_askill_active", table_name="agent_skill")
    op.drop_column("agent_skill", "skill_type")
