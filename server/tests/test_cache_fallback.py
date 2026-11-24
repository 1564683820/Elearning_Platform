import unittest
from unittest.mock import AsyncMock, patch
from redis.exceptions import AuthenticationError, ConnectionError
from app.utils.redis_client import RedisCache, cache_get_or_set


class CacheFallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        reset = patch('app.utils.redis_client._redis_unavailable', False)
        reset.start()
        self.addCleanup(reset.stop)

    async def test_all_operations_are_safe_without_redis(self):
        cache = RedisCache(None)
        cases = [
            ('get', ('k',), None), ('set', ('k', 'v'), False),
            ('delete', ('k',), 0), ('exists', ('k',), False),
            ('expire', ('k', 5), False), ('get_json', ('k',), None),
            ('set_json', ('k', {}), False), ('hget', ('k', 'f'), None),
            ('hset', ('k', 'f', 'v'), 0), ('hgetall', ('k',), {}),
            ('hsetall', ('k', {'f': 'v'}), False), ('hdel', ('k', 'f'), 0),
            ('lrange', ('k',), []), ('lpush', ('k', 'v'), 0),
            ('rpush', ('k', 'v'), 0), ('ltrim', ('k', 0, 1), False),
            ('incr', ('k',), 0), ('incr_with_ttl', ('k', 5), 0),
            ('delete_pattern', ('k*',), 0),
        ]
        for name, args, expected in cases:
            with self.subTest(operation=name):
                self.assertEqual(await getattr(cache, name)(*args), expected)

    async def test_live_cache_keeps_prefix_and_ttl(self):
        redis = AsyncMock()
        redis.set.return_value = True
        cache = RedisCache(redis)
        self.assertTrue(await cache.set('word', 'value', ex=30))
        redis.set.assert_awaited_once_with(cache.PREFIX + 'word', 'value', ex=30)

    async def test_auth_failure_does_not_break_following_operations(self):
        redis = AsyncMock()
        redis.get.side_effect = AuthenticationError('test')
        cache = RedisCache(redis)
        self.assertIsNone(await cache.get('k'))
        self.assertEqual(await cache.delete('k'), 0)

    async def test_hash_expiry_failure_degrades(self):
        redis = AsyncMock()
        redis.hset.return_value = 1
        redis.expire.side_effect = ConnectionError('test')
        self.assertEqual(await RedisCache(redis).hset('k', 'f', 'v', ex=5), 1)

    async def test_cache_miss_without_service_calls_factory_once(self):
        factory = AsyncMock(return_value={'word': 'test'})
        self.assertEqual(await cache_get_or_set(RedisCache(None), 'k', factory), {'word': 'test'})
        factory.assert_awaited_once()
