#!/usr/bin/env python3
"""
Quota tracking and caching layer to protect free-tier API quotas.

TTLs:
  - fixtures / schedules: 4 hours (14,400s)
  - standings: 8 hours (28,800s)
  - teams / players / rosters: 24 hours (86,400s)
  - live data: 2 minutes (120s)

Free-tier budgets:
  - API-Sports: 100 requests / day PER sport (stop calling when reaching threshold e.g. 90)
  - football-data.org: 10 requests / minute
  - balldontlie: 30 requests / minute
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
QUOTA_FILE = CACHE_DIR / "quota_tracker.json"

DEFAULT_TTLS = {
    "fixtures": 14400,     # 4 hours
    "standings": 28800,    # 8 hours
    "teams": 86400,        # 24 hours
    "players": 86400,      # 24 hours
    "live": 120,           # 2 minutes
    "default": 14400,
}

DAILY_BUDGETS = {
    # Provider -> Sport -> Max requests allowed per day
    "api-sports": {
        "default": 90,     # Hard limit is 100/day/sport on free tier; keep safety margin
    },
    "football-data": {
        "default": 500,
    },
    "balldontlie": {
        "default": 1000,
    },
}


class DiskCache:
    """Manages disk-backed response cache with configurable TTLs."""

    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, namespace: str, key: str) -> Path:
        hashed = hashlib.sha256(key.encode("utf-8")).hexdigest()
        ns_dir = self.cache_dir / namespace
        ns_dir.mkdir(parents=True, exist_ok=True)
        return ns_dir / f"{hashed}.json"

    def get(self, namespace: str, key: str, ttl_type: str = "default") -> Optional[Any]:
        path = self._cache_path(namespace, key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            cached_at = payload.get("cached_at", 0)
            ttl = DEFAULT_TTLS.get(ttl_type, DEFAULT_TTLS["default"])
            if time.time() - cached_at > ttl:
                return None  # expired
            return payload.get("data")
        except Exception:
            return None

    def get_stale(self, namespace: str, key: str) -> Optional[tuple[Any, float]]:
        """Return cached data even if expired (used as fallback when API fails)."""
        path = self._cache_path(namespace, key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload.get("data"), payload.get("cached_at", 0)
        except Exception:
            return None

    def set(self, namespace: str, key: str, data: Any):
        path = self._cache_path(namespace, key)
        payload = {
            "cached_at": time.time(),
            "data": data,
        }
        try:
            path.write_text(json.dumps(payload), encoding="utf-8")
        except Exception as err:
            print(f"Warning: Failed to write cache {path}: {err}", file=sys.stderr)


class QuotaTracker:
    """Tracks daily API requests per provider and per sport."""

    def __init__(self, quota_file: Path = QUOTA_FILE):
        self.quota_file = quota_file
        self.quota_file.parent.mkdir(parents=True, exist_ok=True)

    def _get_today_str(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _read_data(self) -> dict:
        if not self.quota_file.is_file():
            return {}
        try:
            return json.loads(self.quota_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_data(self, data: dict):
        try:
            self.quota_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as err:
            print(f"Warning: Failed to write quota file: {err}", file=sys.stderr)

    def get_usage(self, provider: str, sport: str = "default") -> int:
        today = self._get_today_str()
        data = self._read_data()
        return data.get(today, {}).get(provider, {}).get(sport, 0)

    def can_request(self, provider: str, sport: str = "default") -> bool:
        """Returns True if within daily budget, False if budget nearly exhausted."""
        usage = self.get_usage(provider, sport)
        provider_budgets = DAILY_BUDGETS.get(provider, {})
        limit = provider_budgets.get(sport, provider_budgets.get("default", 100))
        return usage < limit

    def record_request(self, provider: str, sport: str = "default"):
        today = self._get_today_str()
        data = self._read_data()
        if today not in data:
            data[today] = {}
        if provider not in data[today]:
            data[today][provider] = {}
        cur = data[today][provider].get(sport, 0)
        data[today][provider][sport] = cur + 1
        self._write_data(data)

    def get_summary(self) -> dict:
        today = self._get_today_str()
        data = self._read_data()
        return data.get(today, {})


# Global singleton instances
cache = DiskCache()
quota = QuotaTracker()
