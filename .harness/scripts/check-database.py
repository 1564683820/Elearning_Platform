"""Read-only startup preflight; never creates databases or runs migrations."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server'))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import get_settings


def failure_hint(code):
    if code in (2002, 2003):
        return ('MySQL is unreachable. Check MYSQL_HOST/MYSQL_PORT and the database service. '
                'For local MySQL80 on Windows, run Start-Service MySQL80 in an administrator PowerShell.')
    if code in (1044, 1045):
        return 'MySQL rejected access. Check MYSQL_USER/MYSQL_PASSWORD and database grants in server/.env.'
    if code == 1049:
        return ('The configured database does not exist. Check MYSQL_DATABASE/WORDS_DATABASE. '
                'This check will not create databases or run migrations.')
    return 'Check the database connection settings and MySQL server logs.'


def main():
    settings = get_settings()
    if not (Path(__file__).resolve().parents[2] / 'server' / '.env').exists():
        print('server/.env is absent; using environment variables / configuration defaults.')
    for label, url in [('main', settings.SYNC_DATABASE_URL), ('words', settings.SYNC_WORDS_DATABASE_URL)]:
        engine = create_engine(url, connect_args={'connect_timeout': 3})
        try:
            with engine.connect() as connection:
                connection.execute(text('SELECT 1'))
        except SQLAlchemyError as error:
            original = getattr(error, 'orig', None)
            code = original.args[0] if original and original.args else 'unknown'
            print(f'Database preflight failed: {label}, MySQL error {code}.')
            print(failure_hint(code))
            print('Configure server/.env using server/.env.example, then run task check-database.')
            return 1
        finally:
            engine.dispose()
    print('Database preflight passed (read-only).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
