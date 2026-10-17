#!/usr/bin/env python3
"""
API-Sports shared provider for SportoCal data scrapers.

Provides fixtures and schedules for: football, basketball, american-football,
baseball, hockey, rugby, volleyball, handball, MMA, afl, tennis.

Free plan: 100 requests/day per sport endpoint.
Auth header: x-apisports-key  (read from env var API_SPORTS_KEY)

Docs: https://www.api-football.com/documentation-v3
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import slugify, make_unique_id_assigner, load_dotenv  # noqa: E402
from unified_models import SportsProvider, Match, Team, League, matches_to_sportocal_data  # noqa: E402
from quota_cache import cache, quota  # noqa: E402

# Ensure .env is loaded
load_dotenv()

# ─── Base URLs per sport ────────────────────────────────────────────────────
BASE_URLS = {
    "football":          "https://v3.football.api-sports.io",
    "afl":               "https://v1.afl.api-sports.io",
    "baseball":          "https://v1.baseball.api-sports.io",
    "basketball":        "https://v1.basketball.api-sports.io",
    "formula-1":         "https://v1.formula-1.api-sports.io",
    "handball":          "https://v1.handball.api-sports.io",
    "hockey":            "https://v1.hockey.api-sports.io",
    "mma":               "https://v1.mma.api-sports.io",
    "nba":               "https://v2.nba.api-sports.io",
    "american-football": "https://v1.american-football.api-sports.io",
    "rugby":             "https://v1.rugby.api-sports.io",
    "volleyball":        "https://v1.volleyball.api-sports.io",
    "tennis":            "https://v1.tennis.api-sports.io",
}


def _get_api_key() -> str:
    key = os.environ.get("API_SPORTS_KEY", "")
    if not key or key == "your_api_sports_key_here":
        return ""
    return key.strip()


class ApiSportsClient(SportsProvider):
    """Client for any API-Sports sport endpoint with quota protection and caching."""

    def __init__(self, sport: str):
        if sport not in BASE_URLS:
            raise ValueError(f"Unknown sport '{sport}'. Known: {list(BASE_URLS)}")
        self.sport = sport
        self.base_url = BASE_URLS[sport]
        self._key = _get_api_key()
        self._session = requests.Session()
        if self._key:
            self._session.headers.update({
                "x-apisports-key": self._key,
                "Accept": "application/json",
            })

    @property
    def provider_name(self) -> str:
        return "api-sports"

    def _get(
        self,
        endpoint: str,
        params: dict | None = None,
        retries: int = 3,
        timeout: int = 20,
        ttl_type: str = "fixtures",
    ) -> dict | None:
        cache_key = f"{self.sport}:{endpoint}:{json.dumps(params or {}, sort_keys=True)}"
        cached_val = cache.get("api-sports", cache_key, ttl_type=ttl_type)
        if cached_val is not None:
            return cached_val

        # Check API key
        if not self._key:
            print(
                f"  [API-Sports/{self.sport}] No valid API_SPORTS_KEY configured.",
                file=sys.stderr,
            )
            # Try stale cache fallback
            stale = cache.get_stale("api-sports", cache_key)
            if stale:
                data, cached_at = stale
                print(f"  [API-Sports/{self.sport}] Using cached fallback from {cached_at}", file=sys.stderr)
                return data
            return None

        # Check quota budget
        if not quota.can_request("api-sports", self.sport):
            print(
                f"  [API-Sports/{self.sport}] Daily request budget near/at limit ({quota.get_usage('api-sports', self.sport)}). Falling back to cache.",
                file=sys.stderr,
            )
            stale = cache.get_stale("api-sports", cache_key)
            return stale[0] if stale else None

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        last_error = None

        for attempt in range(1, retries + 1):
            try:
                quota.record_request("api-sports", self.sport)
                res = self._session.get(url, params=params, timeout=timeout)
            except requests.RequestException as err:
                last_error = err
                if attempt < retries:
                    time.sleep(1.5 ** attempt)
                continue

            if res.status_code == 429:
                retry_after = float(res.headers.get("Retry-After", 60))
                print(f"  [API-Sports/{self.sport}] 429 rate-limited - sleeping {retry_after}s", file=sys.stderr)
                time.sleep(retry_after)
                continue

            if res.status_code == 401:
                print(f"  [API-Sports/{self.sport}] 401 Unauthorized - verify API_SPORTS_KEY", file=sys.stderr)
                stale = cache.get_stale("api-sports", cache_key)
                return stale[0] if stale else None

            if res.status_code != 200:
                print(f"  [API-Sports/{self.sport}] HTTP {res.status_code} for {url}", file=sys.stderr)
                stale = cache.get_stale("api-sports", cache_key)
                return stale[0] if stale else None

            try:
                data = res.json()
                errors = data.get("errors")
                if errors:
                    print(f"  [API-Sports/{self.sport}] API returned errors: {errors}", file=sys.stderr)
                cache.set("api-sports", cache_key, data)
                return data
            except ValueError as err:
                last_error = err
                continue

        print(f"  [API-Sports/{self.sport}] Failed after {retries} attempts: {last_error}", file=sys.stderr)
        stale = cache.get_stale("api-sports", cache_key)
        return stale[0] if stale else None

    # ── Implementation of SportsProvider ──────────────────────────────────────

    def get_matches_by_date(self, sport: str, date: str) -> list[Match]:
        """Fetch all matches across all leagues for this sport on a single date (YYYY-MM-DD)."""
        endpoint = "fixtures" if sport == "football" else "games"
        data = self._get(endpoint, {"date": date}, ttl_type="fixtures")
        items = (data or {}).get("response", [])
        return self._map_raw_items_to_matches(items, sport=sport)

    def get_live_matches(self, sport: str) -> list[Match]:
        """Fetch live matches currently in progress."""
        endpoint = "fixtures" if sport == "football" else "games"
        data = self._get(endpoint, {"live": "all"}, ttl_type="live")
        items = (data or {}).get("response", [])
        return self._map_raw_items_to_matches(items, sport=sport)

    def get_league_matches(
        self, league_id: Any, date_from: str, date_to: str, sport: str = "football"
    ) -> list[Match]:
        """Fetch matches for a specific league within date_from and date_to (YYYY-MM-DD)."""
        raw_items = self.get_fixtures_by_date_range(int(league_id), 0, date_from, date_to)
        return self._map_raw_items_to_matches(raw_items, sport=sport, league_id=str(league_id))

    # ── Raw fetching helpers ──────────────────────────────────────────────────

    def get_fixtures_by_date_range(
        self, league_id: int, season: int, date_from: str, date_to: str
    ) -> list[dict]:
        results = []
        params: dict[str, Any] = {
            "league": league_id,
            "from": date_from,
            "to": date_to,
        }
        if season > 0:
            params["season"] = season

        data = self._get("fixtures", params, ttl_type="fixtures")
        if data:
            results.extend(data.get("response", []))
            pagination = data.get("paging") or {}
            total_pages = pagination.get("total") or 1
            for page in range(2, total_pages + 1):
                page_params = {**params, "page": page}
                more = self._get("fixtures", page_params, ttl_type="fixtures")
                if more:
                    results.extend(more.get("response", []))
                time.sleep(0.2)
        return results

    def _map_raw_items_to_matches(
        self, items: list[dict], sport: str, league_id: str = ""
    ) -> list[Match]:
        matches = []
        assign_id = make_unique_id_assigner()

        for item in items:
            utc = extract_date_from_fixture(item)
            if not utc:
                continue
            name = extract_fixture_name(item) or extract_game_name(item)
            if not name:
                continue

            date_part = utc[:10]
            l_info = item.get("league") or {}
            l_id = str(l_info.get("id") or league_id or sport)
            l_name = l_info.get("name") or sport.title()
            weekend = extract_round_label(item) or date_part
            base_id = f"{slugify(l_name)}-{date_part}-{slugify(name)}"

            # Extract teams
            teams = item.get("teams") or {}
            home_data = teams.get("home") or {}
            away_data = teams.get("away") or {}
            home_team = Team(
                id=str(home_data.get("id", "")),
                name=str(home_data.get("name", "")),
                short_name=home_data.get("code"),
            ) if home_data else None
            away_team = Team(
                id=str(away_data.get("id", "")),
                name=str(away_data.get("name", "")),
                short_name=away_data.get("code"),
            ) if away_data else None

            matches.append(
                Match(
                    id=assign_id(base_id),
                    name=name,
                    utc=utc,
                    sport=sport,
                    league_id=l_id,
                    league_name=l_name,
                    weekend=weekend,
                    home_team=home_team,
                    away_team=away_team,
                )
            )

        matches.sort(key=lambda m: m.utc)
        return matches


# ── Extraction helpers ───────────────────────────────────────────────────────

def _to_utc_iso(date_str: str | None) -> str | None:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return None


def extract_fixture_name(fixture: dict) -> str | None:
    teams = fixture.get("teams") or {}
    home = (teams.get("home") or {}).get("name", "").strip()
    away = (teams.get("away") or {}).get("name", "").strip()
    if home and away:
        return f"{home} v {away}"
    name = (fixture.get("fixture") or {}).get("name") or fixture.get("name")
    return str(name).strip() if name else None


def extract_game_name(game: dict) -> str | None:
    teams = game.get("teams") or {}
    home = (teams.get("home") or {}).get("name", "").strip()
    away = (teams.get("away") or {}).get("name", "").strip()
    if home and away:
        return f"{home} v {away}"
    name = game.get("name") or game.get("title")
    return str(name).strip() if name else None


def extract_date_from_fixture(fixture: dict) -> str | None:
    d = (fixture.get("fixture") or {}).get("date")
    if d:
        return _to_utc_iso(d)
    d = fixture.get("date") or fixture.get("scheduled")
    if isinstance(d, dict):
        d = d.get("start") or d.get("date")
    return _to_utc_iso(str(d)) if d else None


def extract_round_label(fixture: dict) -> str | None:
    league_info = fixture.get("league") or {}
    rnd = league_info.get("round")
    if rnd and isinstance(rnd, str):
        return rnd.strip()
    rnd = fixture.get("round") or fixture.get("week") or fixture.get("stage")
    if rnd:
        return str(rnd).strip()
    return None


def build_events_from_fixtures(
    fixtures: list[dict],
    id_prefix: str,
    sport_key: str,
) -> list[dict]:
    """Convert API-Sports fixture/game dicts into SportoCal event dicts."""
    assign_id = make_unique_id_assigner()
    events = []

    for fix in fixtures:
        utc = extract_date_from_fixture(fix)
        if not utc:
            continue
        name = extract_fixture_name(fix) or extract_game_name(fix)
        if not name:
            continue

        date_part = utc[:10]
        base_id = f"{id_prefix}-{date_part}-{slugify(name)}"
        weekend = extract_round_label(fix) or date_part

        events.append({
            "id": assign_id(base_id),
            "weekend": weekend,
            "name": name,
            "utc": utc,
        })

    events.sort(key=lambda x: x["utc"])
    return events


def write_league_file(
    output_path: Path,
    sport_key: str,
    league_name: str,
    date_from: str,
    date_to: str,
    events: list[dict],
    min_events: int = 1,
) -> bool:
    """Write events to output_path in SportoCal JSON format. Returns True on success."""
    if len(events) < min_events:
        print(
            f"  WARNING: only {len(events)} events (min {min_events}). "
            "Not overwriting existing data.",
            file=sys.stderr,
        )
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "sportKey": sport_key,
        "leagueName": league_name,
        "windowFrom": date_from,
        "windowTo": date_to,
        "events": events,
    }
    output_path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"  Wrote {len(events)} events -> {output_path}", file=sys.stderr)
    return True
