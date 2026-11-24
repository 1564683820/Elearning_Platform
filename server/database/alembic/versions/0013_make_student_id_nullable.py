"""Make exam_submission.student_id nullable for scan grading

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-05 18:45:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 先把已有的 student_id=0 记录改为 NULL（MySQL唯一约束对NULL不检测重复）
    op.execute("UPDATE exam_submission SET student_id = NULL WHERE student_id = 0")
    # 修改列为可空
    op.alter_column(
        "exam_submission",
        "student_id",
        existing_type=sa.BigInteger(),
        nullable=True,
        existing_server_default=None,
        comment="学生ID（扫描批卷未识别考号时可为NULL）",
    )


def downgrade() -> None:
    # 把 NULL 改回 0
    op.execute("UPDATE exam_submission SET student_id = 0 WHERE student_id IS NULL")
    op.alter_column(
        "exam_submission",
        "student_id",
        existing_type=sa.BigInteger(),
        nullable=False,
        existing_server_default=None,
        comment="学生ID",
    )
