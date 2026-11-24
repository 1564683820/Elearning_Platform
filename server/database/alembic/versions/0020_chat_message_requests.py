"""Idempotent requests and their replies reuse existing chat-message rows."""
from alembic import op
import sqlalchemy as sa

revision = "0020_chat_message_requests"
down_revision = "0019_skill_source_filename"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("chat_message") as table:
        table.add_column(sa.Column("request_id", sa.String(64), nullable=True))
        table.add_column(sa.Column("reply_to_message_id", sa.BigInteger(), nullable=True))
        table.create_unique_constraint("uq_chat_message_request", ["conversation_id", "request_id"])
        table.create_unique_constraint("uq_chat_message_reply", ["reply_to_message_id"])


def downgrade():
    with op.batch_alter_table("chat_message") as table:
        table.drop_constraint("uq_chat_message_reply", type_="unique")
        table.drop_constraint("uq_chat_message_request", type_="unique")
        table.drop_column("reply_to_message_id")
        table.drop_column("request_id")
