# ── Monkey-patch: 修复 SQLAlchemy 2.0.23 + pymysql 2.2.x + aiomysql 组合
# AsyncAdapt_aiomysql_connection.ping(self, reconnect) 缺少默认值，
# 而 pymysql 2.2 的 ping(reconnect=False) 默认值 False 导致 SQLAlchemy
# 的 _send_false_to_ping = False，进而调用 ping() 不带参数报错。
import sqlalchemy.dialects.mysql.aiomysql as _aiomysql_dialect

_orig_ping = _aiomysql_dialect.AsyncAdapt_aiomysql_connection.ping


def _patched_ping(self, reconnect=True):
    return _orig_ping(self, reconnect)


_aiomysql_dialect.AsyncAdapt_aiomysql_connection.ping = _patched_ping

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import get_settings

settings = get_settings()

# ── 主数据库引擎（用户/班级/教材/试卷等） ──
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_use_lifo=True,  # LIFO 策略：避免长SSE连接独占空闲连接
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖：获取主库异步数据库会话

    expire_on_commit=False 确保 commit 后对象仍可用。
    请求结束时自动提交（仅提交已提交的事务，不会额外提交空事务）。
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── 单词数据库引擎（dict_word / stage_word 等） ──
words_engine = create_async_engine(
    settings.WORDS_DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_use_lifo=True,
)

words_session = async_sessionmaker(words_engine, class_=AsyncSession, expire_on_commit=False)


class WordBase(DeclarativeBase):
    """单词库的 DeclarativeBase"""
    pass


async def get_words_db() -> AsyncSession:
    """FastAPI 依赖：获取单词库异步数据库会话"""
    async with words_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
