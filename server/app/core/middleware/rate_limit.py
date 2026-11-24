"""
AI 调用限流中间件
- 每用户每分钟最多 N 次 AI 调用
- 使用 Redis 计数器实现
- Redis 不可用时自动跳过限流
"""
import logging
from fastapi import Request, HTTPException, status
from app.utils.redis_client import get_redis, RedisCache

logger = logging.getLogger("rate_limit")


class AIRateLimiter:
    """AI 调用限流器"""

    # 每用户每分钟最大调用次数
    MAX_REQUESTS_PER_MINUTE = 60
    # 每用户每天最大调用次数
    MAX_REQUESTS_PER_DAY = 2000

    @staticmethod
    async def check_rate_limit(user_id: int) -> None:
        """检查用户是否超过 AI 调用限流，超限则抛出 HTTP 429
        Redis 不可用时跳过限流检查"""
        redis = await get_redis()
        if redis is None:
            logger.debug("Redis 不可用，跳过 AI 限流检查")
            return
        cache = RedisCache(redis)

        # 每分钟限流
        minute_key = f"ratelimit:ai:{user_id}:min"
        minute_count = await cache.incr_with_ttl(minute_key, ttl=60)
        if minute_count > AIRateLimiter.MAX_REQUESTS_PER_MINUTE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"AI 调用过于频繁，每分钟最多 {AIRateLimiter.MAX_REQUESTS_PER_MINUTE} 次",
            )

        # 每日限流
        day_key = f"ratelimit:ai:{user_id}:day"
        day_count = await cache.incr_with_ttl(day_key, ttl=86400)
        if day_count > AIRateLimiter.MAX_REQUESTS_PER_DAY:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"今日 AI 调用次数已达上限 ({AIRateLimiter.MAX_REQUESTS_PER_DAY} 次/天)",
            )
