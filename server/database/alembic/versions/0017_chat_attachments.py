"""Bind private user documents to their original teaching-assistant message."""
from alembic import op
import sqlalchemy as sa

revision = "0017_chat_attachments"
down_revision = "0016_exam_sources"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_document", sa.Column("chat_message_id", sa.BigInteger(), nullable=True, comment="会话附件所属消息"))
    op.create_index("ix_user_document_chat_message_id", "user_document", ["chat_message_id"])


def downgrade():
    op.drop_index("ix_user_document_chat_message_id", table_name="user_document")
    op.drop_column("user_document", "chat_message_id")
