"""
Redis 异步客户端封装
- 单例模式，全局共享连接池
- 提供 get/set/delete/hash 等常用操作的异步封装
- 自动添加前缀，支持 TTL
- Redis 不可用时优雅降级，不阻塞业务
"""

import json
import logging
from typing import Optional, Any

import redis.asyncio as aioredis
from redis.exceptions import AuthenticationError
from app.core.config import get_settings

_settings = get_settings()
logger = logging.getLogger("redis")

# 全局连接池（延迟初始化）
_redis: Optional[aioredis.Redis] = None
# Redis 不可用标记（连接失败一次后不再重试）
_redis_unavailable: bool = False


async def get_redis() -> Optional[aioredis.Redis]:
    """获取 Redis 连接（单例），连接失败时返回 None"""
    global _redis, _redis_unavailable
    if _redis_unavailable:
        return None
    if _redis is None:
        try:
            _redis = aioredis.from_url(
                _settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
            )
            # 验证连接是否可用
            await _redis.ping()
            logger.info("Redis 连接成功")
        except Exception as e:
            logger.warning("Redis 不可用 (%s)，缓存和限流功能将跳过", e)
            _redis_unavailable = True
            _redis = None
            return None
    return _redis


def is_redis_available() -> bool:
    """检查 Redis 是否可用"""
    return not _redis_unavailable


async def close_redis():
    """关闭 Redis 连接池"""
    global _redis, _redis_unavailable
    if _redis:
        try:
            await _redis.close()
        except Exception:
            pass
        _redis = None
    _redis_unavailable = False  # 重置标记，允许下次重启后重试


class RedisCache:
    """带前缀的 Redis 缓存工具类，Redis 不可用时自动降级"""

    PREFIX = _settings.REDIS_PREFIX  # "elearn:"

    def __init__(self, redis: Optional[aioredis.Redis]):
        self._r = redis

    @property
    def _available(self) -> bool:
        """Redis 是否可用"""
        return self._r is not None

    def _key(self, key: str) -> str:
        return f"{self.PREFIX}{key}"

    async def _safe_call(self, method: str, *args, **kwargs):
        """执行 Redis 操作，连接/AUTH 失败时标记不可用并返回降级值"""
        if not self._available:
            return None
        try:
            return await getattr(self._r, method)(*args, **kwargs)
        except AuthenticationError:
            global _redis_unavailable
            _redis_unavailable = True
            self._r = None
            logger.warning("Redis 认证失败，标记为不可用，后续操作将跳过")
            return None
        except Exception:
            # 其他连接错误也降级，但不永久标记不可用
            return None

    # ---------- String 操作 ----------

    async def get(self, key: str) -> Optional[str]:
        return await self._safe_call('get', self._key(key))

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """ex: 过期秒数"""
        result = await self._safe_call('set', self._key(key), value, ex=ex)
        return bool(result) if result is not None else False

    async def delete(self, key: str) -> int:
        result = await self._safe_call('delete', self._key(key))
        return result if result is not None else 0

    async def exists(self, key: str) -> bool:
        result = await self._safe_call('exists', self._key(key))
        return result if result is not None else False

    async def expire(self, key: str, seconds: int) -> bool:
        result = await self._safe_call('expire', self._key(key), seconds)
        return bool(result) if result is not None else False

    # ---------- JSON 操作（序列化/反序列化） ----------

    async def get_json(self, key: str) -> Optional[Any]:
        raw = await self.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set_json(self, key: str, value: Any, ex: int | None = None) -> bool:
        return await self.set(key, json.dumps(value, ensure_ascii=False), ex=ex)

    # ---------- Hash 操作 ----------

    async def hget(self, key: str, field: str) -> Optional[str]:
        return await self._safe_call('hget', self._key(key), field)

    async def hset(self, key: str, field: str, value: str, ex: int | None = None) -> int:
        result = await self._safe_call('hset', self._key(key), field, value)
        if result is not None and ex:
            await self._safe_call('expire', self._key(key), ex)
        return result if result is not None else 0

    async def hgetall(self, key: str) -> dict[str, str]:
        result = await self._safe_call('hgetall', self._key(key))
        return result if result is not None else {}

    async def hsetall(self, key: str, mapping: dict[str, str], ex: int | None = None) -> bool:
        k = self._key(key)
        result = await self._safe_call('hset', k, mapping=mapping)
        if result is not None and ex:
            await self._safe_call('expire', k, ex)
        return result is not None

    async def hdel(self, key: str, *fields: str) -> int:
        result = await self._safe_call('hdel', self._key(key), *fields)
        return result if result is not None else 0

    # ---------- List 操作 ----------

    async def lrange(self, key: str, start: int = 0, stop: int = -1) -> list[str]:
        result = await self._safe_call('lrange', self._key(key), start, stop)
        return result if result is not None else []

    async def lpush(self, key: str, *values: str) -> int:
        result = await self._safe_call('lpush', self._key(key), *values)
        return result if result is not None else 0

    async def rpush(self, key: str, *values: str) -> int:
        result = await self._safe_call('rpush', self._key(key), *values)
        return result if result is not None else 0

    async def ltrim(self, key: str, start: int, stop: int) -> bool:
        result = await self._safe_call('ltrim', self._key(key), start, stop)
        return bool(result) if result is not None else False

    # ---------- 限流（计数器） ----------

    async def incr(self, key: str) -> int:
        result = await self._safe_call('incr', self._key(key))
        return result if result is not None else 0

    async def incr_with_ttl(self, key: str, ttl: int) -> int:
        """自增并设置 TTL（仅在 key 新建时），Redis 不可用时返回 0（不限流）"""
        k = self._key(key)
        count = await self._safe_call('incr', k)
        if count is not None and count == 1:
            await self._safe_call('expire', k, ttl)
        return count if count is not None else 0

    # ---------- 批量删除（通配符） ----------

    async def delete_pattern(self, pattern: str) -> int:
        """删除匹配模式的所有 key（慎用，生产环境大key量时改用 scan）"""
        if not self._available:
            return 0
        keys = []
        async for k in self._r.scan_iter(match=self._key(pattern)):
            keys.append(k)
        if keys:
            return await self._r.delete(*keys)
        return 0


# ---------- 便捷函数：缓存穿透模式 ----------

async def cache_get_or_set(
    cache: RedisCache,
    key: str,
    factory,  # async callable
    ex: int = 3600,
) -> Any:
    """Cache-Aside 模式：先读缓存，miss 则执行 factory 写入缓存
    Redis 不可用时直接调用 factory 并返回结果"""
    if not cache._available:
        return await factory()

    data = await cache.get_json(key)
    if data is not None:
        return data

    result = await factory()
    if result is not None:
        await cache.set_json(key, result, ex=ex)
    return result
