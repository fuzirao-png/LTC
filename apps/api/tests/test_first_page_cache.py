import unittest
from unittest.mock import Mock

from redis.exceptions import ConnectionError

from ltc.platform.first_page_cache import FirstPageCache


class FirstPageCacheTests(unittest.TestCase):
    def setUp(self):
        self.cache = FirstPageCache("")
        self.redis = self.cache._redis = Mock()
        self.load = Mock(return_value=[{"company_name": "example"}])

    def test_redis_miss_loads_and_stores_first_page_for_thirty_seconds(self):
        self.redis.get.return_value = None
        self.assertEqual(self.load.return_value, self.cache.get_or_load(("mine", "user-a", 100), self.load))
        key = self.redis.get.call_args.args[0]
        self.redis.set.assert_called_once_with(key, '[{"company_name": "example"}]', ex=30, nx=True)

    def test_hits_are_scoped_and_refresh_replaces_the_cached_page(self):
        self.redis.get.return_value = b'[{"company_name": "cached"}]'
        first = ("mine", "user-a", 100)
        second = ("mine", "user-b", 100)
        self.assertEqual([{"company_name": "cached"}], self.cache.get_or_load(first, self.load))
        self.cache.get_or_load(second, self.load)
        key_a, key_b = (call.args[0] for call in self.redis.get.call_args_list)
        self.assertNotEqual(key_a, key_b)
        self.load.assert_not_called()

        self.assertEqual(self.load.return_value, self.cache.get_or_load(first, self.load, refresh=True))
        self.redis.set.assert_called_once_with(key_a, '[{"company_name": "example"}]', ex=30, nx=False)

    def test_redis_failure_does_not_break_postgres_fallback(self):
        self.redis.get.side_effect = ConnectionError
        self.redis.set.side_effect = ConnectionError
        self.assertEqual(self.load.return_value, self.cache.get_or_load(("pool", "user-a"), self.load))
        self.load.assert_called_once_with()
