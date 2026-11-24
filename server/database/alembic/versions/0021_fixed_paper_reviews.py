"""Fixed-card review state and active grade identity on existing grading tables."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import INTEGER

revision = "0021_fixed_paper_reviews"
down_revision = "0020_chat_message_requests"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("exam_scan_record") as table:
        table.add_column(sa.Column("request_id", sa.String(64), nullable=True))
        table.add_column(sa.Column("status", sa.String(16), nullable=True))
        table.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        table.create_unique_constraint("uq_scan_exam_request", ["exam_id", "teacher_id", "request_id"])
        table.create_index("ix_scan_exam_updated", ["exam_id", "updated_at", "id"])
    with op.batch_alter_table("exam_submission") as table:
        table.add_column(sa.Column("grade_version", sa.Integer().with_variant(INTEGER(unsigned=True), "mysql"),
                                   nullable=False, server_default="0"))
        table.add_column(sa.Column("unmatched_exam_number", sa.String(64), sa.Computed(
            "CASE WHEN student_id IS NULL AND grade_version > 0 THEN NULLIF(TRIM(exam_number), '') ELSE NULL END",
            persisted=False,
        )))
        table.create_unique_constraint("uq_exam_unmatched_number", ["exam_id", "unmatched_exam_number"])


def downgrade():
    with op.batch_alter_table("exam_submission") as table:
        table.drop_constraint("uq_exam_unmatched_number", type_="unique")
        table.drop_column("unmatched_exam_number")
        table.drop_column("grade_version")
    with op.batch_alter_table("exam_scan_record") as table:
        table.drop_index("ix_scan_exam_updated")
        table.drop_constraint("uq_scan_exam_request", type_="unique")
        for column in ("updated_at", "status", "request_id"):
            table.drop_column(column)
