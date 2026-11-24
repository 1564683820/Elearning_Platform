"""Create only the two approved, empty local demo databases. Never drop or overwrite."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.core.config import get_settings


def main():
    settings = get_settings()
    names = ('elearning_agent_dev', 'elearning_agent_words_dev')
    if (settings.MYSQL_DATABASE, settings.WORDS_DATABASE) != names or settings.MYSQL_HOST not in ('127.0.0.1', 'localhost', '::1'):
        raise RuntimeError('Only the two approved local demo databases may be created')
    engine = create_engine(make_url(settings.SYNC_DATABASE_URL).set(database=None))
    with engine.connect() as connection:
        for name in names:
            occupied = connection.execute(text('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=:name'), {'name': name}).scalar()
            if occupied:
                raise RuntimeError('Demo database is occupied; refusing initialization')
        for name in names:
            # Names are fixed constants, never supplied by a request.
            connection.execute(text(f'CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4'))
        connection.commit()
    engine.dispose()
    print('The two isolated empty demo databases are ready for migration.')


if __name__ == '__main__':
    main()
