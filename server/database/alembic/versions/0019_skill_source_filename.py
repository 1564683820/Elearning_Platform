"""Preserve the original filename for a teacher's question-answering skill."""
from alembic import op
import sqlalchemy as sa

revision = "0019_skill_source_filename"
down_revision = "0018_archive_templates"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_skill", sa.Column("source_filename", sa.String(256), nullable=True))


def downgrade():
    op.drop_column("agent_skill", "source_filename")
