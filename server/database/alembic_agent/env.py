"""Independent frozen demo schema chain; never points at legacy/production databases."""
from alembic import context
from sqlalchemy import create_engine, text
from app.core.config import get_settings

settings = get_settings()
if (settings.MYSQL_DATABASE != 'elearning_agent_dev' or settings.WORDS_DATABASE != 'elearning_agent_words_dev'
        or settings.MYSQL_HOST not in ('127.0.0.1', 'localhost', '::1')):
    raise RuntimeError('Demo migrations require elearning_agent_dev / elearning_agent_words_dev')

if context.is_offline_mode():
    context.configure(url=settings.SYNC_DATABASE_URL, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(settings.SYNC_DATABASE_URL)
    with engine.connect() as connection:
        # A fresh chain must never be used to stamp or reshape an existing schema.
        version_exists = connection.execute(text("SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = :db AND table_name = 'alembic_version'"),
            {'db': settings.MYSQL_DATABASE}).scalar()
        current = connection.execute(text('SELECT version_num FROM alembic_version')).scalar() if version_exists else None
        if current and current != 'agent_0001':
            raise RuntimeError('Unrecognized schema revision; refusing demo migration')
        if current is None:
            occupied = connection.execute(text("SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema IN (:main, :words) AND table_name <> 'alembic_version'"),
                {'main': settings.MYSQL_DATABASE, 'words': settings.WORDS_DATABASE}).scalar()
            if occupied:
                raise RuntimeError('Demo baseline requires two empty databases')
        connection.commit()
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
