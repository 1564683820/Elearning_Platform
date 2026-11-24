"""Frozen schema for the two specifically named, empty teaching demo databases.

No application metadata imports: future model changes cannot rewrite this revision.
MySQL DDL is not transactional; never run this against an occupied/legacy database.
"""
from pathlib import Path
from alembic import op

revision = 'agent_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    root = Path(__file__).resolve().parents[1] / 'schema'
    for name in ('main', 'words'):
        if name == 'words':
            op.execute('USE elearning_agent_words_dev')
        for statement in (root / f'{name}.sql').read_text(encoding='utf-8').split(';\n'):
            if statement.strip():
                op.execute(statement)
    op.execute('USE elearning_agent_dev')


def downgrade():
    raise RuntimeError('Demo baseline downgrade deletes data and requires a separately authorized reset')
