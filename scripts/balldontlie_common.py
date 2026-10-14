#!/usr/bin/env python3
"""
BALLDONTLIE shared provider for SportoCal data scrapers.

Free tier covers NBA games (v1 API).
Auth header: Authorization: <key>  (read from env var BALLDONTLIE_KEY)

Free tier rate limit: 30 requests/minute.
Docs: https://docs.balldontlie.io
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import slugify, make_unique_id_assigner, load_dotenv  # noqa: E402
from unified_models import SportsProvider, Match, Team, League  # noqa: E402
from quota_cache import cache, quota  # noqa: E402

# Ensure .env is loaded
load_dotenv()

BASE_URL = "https://api.balldontlie.io/v1"


def _get_api_key() -> str:
    key = os.environ.get("BALLDONTLIE_KEY", "")
    if not key or key == "your_balldontlie_key_here":
        return ""
    return key.strip()


class BallDontLieProvider(SportsProvider):
    """Client for BALLDONTLIE API with caching and quota tracking."""

    def __init__(self):
        self._key = _get_api_key()
        self._last_request_time = 0.0

    @property
    def provider_name(self) -> str:
        return "balldontlie"

    def _rate_limit_wait(self):
        # 30 req/minute -> minimum 2.1s between calls
        elapsed = time.time() - self._last_request_time
        if elapsed < 2.1:
            time.sleep(2.1 - elapsed)
        self._last_request_time = time.time()

    def _get(
        self,
        endpoint: str,
        params: dict | None = None,
        retries: int = 4,
        timeout: int = 20,
        ttl_type: str = "fixtures",
    ) -> dict | None:
        cache_key = f"{endpoint}:{json.dumps(params or {}, sort_keys=True)}"
        cached_val = cache.get("balldontlie", cache_key, ttl_type=ttl_type)
        if cached_val is not None:
            return cached_val

        if not self._key:
            print("  [BALLDONTLIE] No valid BALLDONTLIE_KEY configured.", file=sys.stderr)
            stale = cache.get_stale("balldontlie", cache_key)
            if stale:
                data, cached_at = stale
                print(f"  [BALLDONTLIE] Using cached fallback from {cached_at}", file=sys.stderr)
                return data
            return None

        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": self._key,
            "Accept": "application/json",
        }
        last_error = None

        for attempt in range(1, retries + 1):
            self._rate_limit_wait()
            try:
                quota.record_request("balldontlie", "basketball")
                res = requests.get(url, headers=headers, params=params, timeout=timeout)
            except requests.RequestException as err:
                last_error = err
                if attempt < retries:
                    time.sleep(2 ** attempt)
                continue

            if res.status_code == 429:
                retry_after = float(res.headers.get("Retry-After", 10))
                print(f"  [BALLDONTLIE] 429 rate-limited - sleeping {retry_after}s", file=sys.stderr)
                time.sleep(retry_after)
                continue

            if res.status_code in (401, 403):
                print(f"  [BALLDONTLIE] HTTP {res.status_code} - verify BALLDONTLIE_KEY", file=sys.stderr)
                stale = cache.get_stale("balldontlie", cache_key)
                return stale[0] if stale else None

            if res.status_code != 200:
                print(f"  [BALLDONTLIE] HTTP {res.status_code} for {url}", file=sys.stderr)
                if attempt < retries:
                    time.sleep(2)
                continue

            try:
                data = res.json()
                cache.set("balldontlie", cache_key, data)
                return data
            except ValueError as err:
                last_error = err
                continue

        print(f"  [BALLDONTLIE] FAILED after {retries} attempts: {last_error}", file=sys.stderr)
        stale = cache.get_stale("balldontlie", cache_key)
        return stale[0] if stale else None

    # ── Implementation of SportsProvider ──────────────────────────────────────

    def get_matches_by_date(self, sport: str, date: str) -> list[Match]:
        """Fetch NBA games on date (date: YYYY-MM-DD)."""
        data = self._get("games", {"dates[]": date, "per_page": 100}, ttl_type="fixtures")
        games = (data or {}).get("data", [])
        return self._map_games(games)

    def get_live_matches(self, sport: str) -> list[Match]:
        """Fetch live NBA games today."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        data = self._get("games", {"dates[]": today, "per_page": 100}, ttl_type="live")
        games = (data or {}).get("data", [])
        # Live games typically have status != 'Final' and period > 0
        live_games = [g for g in games if g.get("status") not in ("Final", None) and g.get("period", 0) > 0]
        return self._map_games(live_games)

    def get_league_matches(
        self, league_id: Any, date_from: str, date_to: str, sport: str = "basketball"
    ) -> list[Match]:
        """Fetch NBA games between start_date and end_date."""
        raw_games = fetch_nba_games(date_from, date_to)
        return self._map_games(raw_games)

    def _map_games(self, games: list[dict]) -> list[Match]:
        assign_id = make_unique_id_assigner()
        results = []

        for game in games:
            date_str = game.get("date")
            utc = _to_utc_iso(date_str)
            if not utc:
                continue

            home_raw = game.get("home_team") or {}
            visitor_raw = game.get("visitor_team") or {}
            home_name = home_raw.get("full_name", "").strip()
            away_name = visitor_raw.get("full_name", "").strip()
            if not home_name or not away_name:
                continue

            name = f"{away_name} v {home_name}"
            date_part = utc[:10]
            base_id = f"nba-{date_part}-{slugify(name)}"

            season = game.get("season")
            weekend = f"Season {season}" if season else date_part

            home_team = Team(
                id=str(home_raw.get("id", "")),
                name=home_name,
                short_name=home_raw.get("abbreviation"),
                code=home_raw.get("abbreviation"),
            )
            away_team = Team(
                id=str(visitor_raw.get("id", "")),
                name=away_name,
                short_name=visitor_raw.get("abbreviation"),
                code=visitor_raw.get("abbreviation"),
            )

            results.append(
                Match(
                    id=assign_id(base_id),
                    name=name,
                    utc=utc,
                    sport="basketball",
                    league_id="nba",
                    league_name="NBA",
                    weekend=weekend,
                    status=game.get("status"),
                    home_team=home_team,
                    away_team=away_team,
                )
            )

        results.sort(key=lambda m: m.utc)
        return results


client = BallDontLieProvider()


def _to_utc_iso(date_str: str | None) -> str | None:
    if not date_str:
        return None
    try:
        if "T" in str(date_str) or "Z" in str(date_str):
            dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(str(date_str), "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=timezone.utc
            )
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return None


def fetch_nba_games(start_date: str, end_date: str) -> list[dict]:
    results = []
    cursor = None

    while True:
        params: dict = {
            "start_date": start_date,
            "end_date": end_date,
            "per_page": 100,
        }
        if cursor is not None:
            params["cursor"] = cursor

        data = client._get("games", params)
        if not data:
            break

        results.extend(data.get("data", []))

        meta = data.get("meta", {})
        next_cursor = meta.get("next_cursor")
        if not next_cursor:
            break
        cursor = next_cursor

    return results


def build_nba_events(games: list[dict], id_prefix: str = "nba") -> list[dict]:
    assign_id = make_unique_id_assigner()
    events = []

    for game in games:
        date_str = game.get("date")
        utc = _to_utc_iso(date_str)
        if not utc:
            continue

        home = (game.get("home_team") or {}).get("full_name", "").strip()
        away = (game.get("visitor_team") or {}).get("full_name", "").strip()
        if not home or not away:
            continue

        name = f"{away} v {home}"
        date_part = utc[:10]
        base_id = f"{id_prefix}-{date_part}-{slugify(name)}"

        season = game.get("season")
        week_label = f"Season {season}" if season else date_part

        events.append({
            "id": assign_id(base_id),
            "weekend": week_label,
            "name": name,
            "utc": utc,
        })

    events.sort(key=lambda x: x["utc"])
    return events
