"""Keep archived answer-sheet templates for historical exam snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "0018_archive_templates"
down_revision = "0017_chat_attachments"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("answer_sheet_template", sa.Column("archived_at", sa.DateTime(), nullable=True, comment="模板停用时间"))


def downgrade():
    op.drop_column("answer_sheet_template", "archived_at")
