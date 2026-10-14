#!/usr/bin/env python3
"""
Unit tests confirming all providers handle missing/placeholder keys gracefully
without crashing or raising uncaught exceptions.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from api_sports_common import ApiSportsClient
from football_data_common import FootballDataProvider
from balldontlie_common import BallDontLieProvider


class TestProvidersWithoutKeys(unittest.TestCase):

    def setUp(self):
        # Ensure env vars are either missing or placeholders
        self.old_env = {
            "API_SPORTS_KEY": os.environ.get("API_SPORTS_KEY"),
            "FOOTBALL_DATA_KEY": os.environ.get("FOOTBALL_DATA_KEY"),
            "BALLDONTLIE_KEY": os.environ.get("BALLDONTLIE_KEY"),
        }
        os.environ["API_SPORTS_KEY"] = "your_api_sports_key_here"
        os.environ["FOOTBALL_DATA_KEY"] = "your_football_data_key_here"
        os.environ["BALLDONTLIE_KEY"] = "your_balldontlie_key_here"

    def tearDown(self):
        for k, v in self.old_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

    def test_api_sports_graceful_missing_key(self):
        client = ApiSportsClient("football")
        res = client.get_matches_by_date("football", "2026-08-15")
        self.assertIsInstance(res, list)
        self.assertEqual(len(res), 0)

    def test_football_data_graceful_missing_key(self):
        provider = FootballDataProvider()
        res = provider.get_matches_by_date("football", "2026-08-15")
        self.assertIsInstance(res, list)
        self.assertEqual(len(res), 0)

    def test_balldontlie_graceful_missing_key(self):
        provider = BallDontLieProvider()
        res = provider.get_matches_by_date("basketball", "2026-10-25")
        self.assertIsInstance(res, list)
        self.assertEqual(len(res), 0)


if __name__ == "__main__":
    unittest.main()
