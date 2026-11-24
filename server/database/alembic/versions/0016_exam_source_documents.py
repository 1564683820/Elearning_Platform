"""Associate existing user documents with paper exam drafts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import SMALLINT

revision = "0016_exam_sources"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_document") as table:
        table.add_column(sa.Column("exam_id", sa.BigInteger(), nullable=True, comment="原件所属试卷"))
        table.add_column(sa.Column("source_order", sa.SmallInteger().with_variant(SMALLINT(unsigned=True), "mysql"),
                                   nullable=True, comment="原件顺序"))
        table.create_unique_constraint("uq_user_document_exam_order", ["exam_id", "source_order"])


def downgrade():
    with op.batch_alter_table("user_document") as table:
        table.drop_constraint("uq_user_document_exam_order", type_="unique")
        table.drop_column("source_order")
        table.drop_column("exam_id")
