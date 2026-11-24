"""Read-only readiness checks. Does not expose secrets or call paid model endpoints."""
import asyncio
import json
import socket
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.core.config import get_settings
from app.db.database import engine, words_engine


async def check():
    settings = get_settings()
    results = {'isolated_databases': settings.MYSQL_DATABASE == 'elearning_agent_dev' and
               settings.WORDS_DATABASE == 'elearning_agent_words_dev',
               'llm_key_configured': bool(settings.LLM_API_KEY),
               'embedding_key_configured': bool(settings.EMBEDDING_API_KEY)}
    for name, db_engine in [('main_database', engine), ('words_database', words_engine)]:
        try:
            async with asyncio.timeout(5):
                async with db_engine.connect() as db:
                    await db.execute(text('SELECT 1'))
            results[name] = True
        except Exception:
            results[name] = False
        finally:
            await db_engine.dispose()
    for name, host, port in [('redis_socket', settings.REDIS_HOST, settings.REDIS_PORT),
                             ('milvus_socket', settings.MILVUS_HOST, settings.MILVUS_PORT)]:
        try:
            with socket.create_connection((host, port), timeout=2):
                results[name] = True
        except OSError:
            results[name] = False
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(results.values()) else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(check()))
