#!/usr/bin/env python3
"""
Unit tests for quota tracking and caching layer.
"""

import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from quota_cache import DiskCache, QuotaTracker


class TestQuotaCache(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.cache = DiskCache(cache_dir=self.test_dir / "cache")
        self.quota = QuotaTracker(quota_file=self.test_dir / "quota.json")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_cache_set_and_get(self):
        self.cache.set("test_ns", "key_1", {"hello": "world"})
        val = self.cache.get("test_ns", "key_1")
        self.assertIsNotNone(val)
        self.assertEqual(val["hello"], "world")

    def test_cache_miss(self):
        val = self.cache.get("test_ns", "non_existent_key")
        self.assertIsNone(val)

    def test_cache_stale_fallback(self):
        self.cache.set("test_ns", "key_stale", {"data": 123})
        # Even if expired or missing fresh TTL, get_stale should return data and timestamp
        stale = self.cache.get_stale("test_ns", "key_stale")
        self.assertIsNotNone(stale)
        data, cached_at = stale
        self.assertEqual(data["data"], 123)
        self.assertGreater(cached_at, 0)

    def test_quota_tracking(self):
        self.assertEqual(self.quota.get_usage("api-sports", "football"), 0)
        self.assertTrue(self.quota.can_request("api-sports", "football"))

        # Record 5 requests
        for _ in range(5):
            self.quota.record_request("api-sports", "football")

        self.assertEqual(self.quota.get_usage("api-sports", "football"), 5)

    def test_quota_limit_enforcement(self):
        # Default budget for api-sports is 90
        for _ in range(90):
            self.quota.record_request("api-sports", "basketball")

        self.assertFalse(self.quota.can_request("api-sports", "basketball"))


if __name__ == "__main__":
    unittest.main()
