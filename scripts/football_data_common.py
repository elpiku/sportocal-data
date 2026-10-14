#!/usr/bin/env python3
"""
football-data.org shared provider for SportoCal data scrapers.

Free tier covers:
  2021 = Premier League (England)
  2001 = UEFA Champions League
  2002 = Bundesliga (Germany)
  2019 = Serie A (Italy)
  2014 = La Liga (Spain)
  2015 = Ligue 1 (France)
  2003 = Eredivisie (Netherlands)
  2017 = Primeira Liga (Portugal)
  2016 = Championship (England)
  2000 = FIFA World Cup
  2018 = European Championship
  2013 = Série A (Brazil)
  2145 = MLS (USA)

Free tier rate limit: 10 requests/minute.
Auth header: X-Auth-Token  (read from env var FOOTBALL_DATA_KEY)

Docs: https://www.football-data.org/documentation/quickstart
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import slugify, make_unique_id_assigner, load_dotenv  # noqa: E402
from unified_models import SportsProvider, Match, Team, League  # noqa: E402
from quota_cache import cache, quota  # noqa: E402

# Ensure .env is loaded
load_dotenv()

BASE_URL = "https://api.football-data.org/v4"

COMPETITION_MAP = {
    2021: ("premierleague",        "Premier League",              "pl"),
    2001: ("uefachampionsleague",  "UEFA Champions League",       "ucl"),
    2002: ("bundesliga",           "Bundesliga",                  "bl"),
    2019: ("seriea",               "Serie A",                     "sa"),
    2014: ("laliga",               "La Liga",                     "ll"),
    2015: ("ligue1",               "Ligue 1",                     "l1"),
    2003: ("eredivisie",           "Eredivisie",                  "ed"),
    2017: ("primeiraliga",         "Primeira Liga",               "por"),
    2016: ("championship",         "EFL Championship",            "ch"),
    2000: ("fifaworldcup",         "FIFA World Cup",              "wc"),
    2018: ("euro",                 "UEFA European Championship",  "euro"),
    2013: ("seriea-brazil",        "Brasileirão Série A",         "bra"),
    2145: ("mls",                  "MLS",                         "mls"),
    2152: ("uefaeuropaleague",     "UEFA Europa League",          "uel"),
    2146: ("uefaconferenceleague", "UEFA Conference League",      "uecl"),
    2114: ("primeradivision-arg",  "Argentine Primera División",  "arg"),
    2119: ("ligamx",               "Liga MX",                     "mx"),
}


def _get_api_key() -> str:
    key = os.environ.get("FOOTBALL_DATA_KEY", "")
    if not key or key == "your_football_data_key_here":
        return ""
    return key.strip()


class FootballDataProvider(SportsProvider):
    """Client for football-data.org v4 API with caching and quota tracking."""

    def __init__(self):
        self._key = _get_api_key()
        self._last_request_time = 0.0

    @property
    def provider_name(self) -> str:
        return "football-data"

    def _rate_limit_wait(self):
        # 10 req/minute -> minimum 6 seconds between requests
        elapsed = time.time() - self._last_request_time
        if elapsed < 6.0:
            time.sleep(6.0 - elapsed)
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
        cached_val = cache.get("football-data", cache_key, ttl_type=ttl_type)
        if cached_val is not None:
            return cached_val

        if not self._key:
            print("  [football-data] No valid FOOTBALL_DATA_KEY configured.", file=sys.stderr)
            stale = cache.get_stale("football-data", cache_key)
            if stale:
                data, cached_at = stale
                print(f"  [football-data] Using cached fallback from {cached_at}", file=sys.stderr)
                return data
            return None

        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        headers = {
            "X-Auth-Token": self._key,
            "Accept": "application/json",
        }
        last_error = None

        for attempt in range(1, retries + 1):
            self._rate_limit_wait()
            try:
                quota.record_request("football-data", "football")
                res = requests.get(url, headers=headers, params=params, timeout=timeout)
            except requests.RequestException as err:
                last_error = err
                if attempt < retries:
                    time.sleep(2 ** attempt)
                continue

            # Inspect official rate limit headers from football-data.org lookup tables
            req_available = res.headers.get("X-RequestsAvailable")
            reset_seconds = res.headers.get("X-RequestCounter-Reset")
            if req_available is not None:
                try:
                    if int(req_available) <= 1:
                        sleep_time = int(reset_seconds) if reset_seconds else 60
                        print(f"  [football-data] Approaching rate limit ({req_available} available), pausing {sleep_time}s...", file=sys.stderr)
                        time.sleep(sleep_time)
                except (ValueError, TypeError):
                    pass

            if res.status_code == 429:
                sleep_time = int(reset_seconds) if reset_seconds else 65
                print(f"  [football-data] 429 rate-limited - sleeping {sleep_time}s", file=sys.stderr)
                time.sleep(sleep_time)
                continue

            if res.status_code in (400, 403, 404):
                print(f"  [football-data] HTTP {res.status_code} for {url}", file=sys.stderr)
                stale = cache.get_stale("football-data", cache_key)
                return stale[0] if stale else None

            if res.status_code != 200:
                print(f"  [football-data] HTTP {res.status_code} for {url}", file=sys.stderr)
                if attempt < retries:
                    time.sleep(2)
                continue

            try:
                data = res.json()
                cache.set("football-data", cache_key, data)
                return data
            except ValueError as err:
                last_error = err
                continue

        print(f"  [football-data] FAILED after {retries} attempts: {last_error}", file=sys.stderr)
        stale = cache.get_stale("football-data", cache_key)
        return stale[0] if stale else None

    # ── Implementation of SportsProvider ──────────────────────────────────────

    def get_matches_by_date(self, sport: str, date: str) -> list[Match]:
        """Fetch all matches on a date (date: YYYY-MM-DD)."""
        data = self._get("matches", {"dateFrom": date, "dateTo": date}, ttl_type="fixtures")
        raw_matches = (data or {}).get("matches", [])
        return self._map_matches(raw_matches)

    def get_live_matches(self, sport: str) -> list[Match]:
        """Fetch currently live matches."""
        data = self._get("matches", {"status": "IN_PLAY"}, ttl_type="live")
        raw_matches = (data or {}).get("matches", [])
        return self._map_matches(raw_matches)

    def get_league_matches(
        self, league_id: Any, date_from: str, date_to: str, sport: str = "football"
    ) -> list[Match]:
        """Fetch matches for a specific competition."""
        data = self._get(
            f"competitions/{league_id}/matches",
            params={"dateFrom": date_from, "dateTo": date_to, "status": "SCHEDULED,FINISHED,IN_PLAY"},
            ttl_type="fixtures",
        )
        raw_matches = (data or {}).get("matches", [])
        return self._map_matches(raw_matches, competition_id=int(league_id) if str(league_id).isdigit() else None)

    def _map_matches(
        self, matches: list[dict], competition_id: Optional[int] = None
    ) -> list[Match]:
        assign_id = make_unique_id_assigner()
        results = []

        for match in matches:
            utc = _to_utc_iso(match.get("utcDate"))
            if not utc:
                continue
            name = _extract_match_name(match)
            if not name:
                continue

            c_info = match.get("competition") or {}
            c_id = c_info.get("id") or competition_id or 0
            if c_id in COMPETITION_MAP:
                sport_key, league_name, id_prefix = COMPETITION_MAP[c_id]
            else:
                sport_key = f"football-{c_id}"
                league_name = c_info.get("name", "Football")
                id_prefix = "fb"

            date_part = utc[:10]
            base_id = f"{id_prefix}-{date_part}-{slugify(name)}"
            weekend = _extract_round_label(match) or date_part

            home_raw = match.get("homeTeam") or {}
            away_raw = match.get("awayTeam") or {}
            home_team = Team(
                id=str(home_raw.get("id", "")),
                name=home_raw.get("name") or home_raw.get("shortName") or "",
                short_name=home_raw.get("shortName") or home_raw.get("tla"),
                code=home_raw.get("tla"),
            )
            away_team = Team(
                id=str(away_raw.get("id", "")),
                name=away_raw.get("name") or away_raw.get("shortName") or "",
                short_name=away_raw.get("shortName") or away_raw.get("tla"),
                code=away_raw.get("tla"),
            )

            results.append(
                Match(
                    id=assign_id(base_id),
                    name=name,
                    utc=utc,
                    sport="football",
                    league_id=str(c_id),
                    league_name=league_name,
                    weekend=weekend,
                    status=match.get("status"),
                    home_team=home_team,
                    away_team=away_team,
                )
            )

        results.sort(key=lambda m: m.utc)
        return results


# ── Global client instance ──────────────────────────────────────────────────
client = FootballDataProvider()


def _to_utc_iso(date_str: str | None) -> str | None:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return None


def fetch_matches(competition_id: int, date_from: str, date_to: str) -> list[dict]:
    data = client._get(
        f"competitions/{competition_id}/matches",
        params={"dateFrom": date_from, "dateTo": date_to, "status": "SCHEDULED,FINISHED,IN_PLAY"},
    )
    if not data:
        return []
    return data.get("matches", [])


def _extract_match_name(match: dict) -> str | None:
    home = (match.get("homeTeam") or {}).get("name") or (match.get("homeTeam") or {}).get("shortName")
    away = (match.get("awayTeam") or {}).get("name") or (match.get("awayTeam") or {}).get("shortName")
    if home and away:
        return f"{home.strip()} v {away.strip()}"
    return None


def _extract_round_label(match: dict) -> str | None:
    matchday = match.get("matchday")
    if matchday:
        return f"Matchday {matchday}"
    stage = match.get("stage")
    group = match.get("group")
    if stage and group:
        return f"{stage} - {group}"
    if stage:
        return stage.replace("_", " ").title()
    return None


def build_events_from_matches(matches: list[dict], id_prefix: str) -> list[dict]:
    assign_id = make_unique_id_assigner()
    events = []

    for match in matches:
        utc = _to_utc_iso(match.get("utcDate"))
        if not utc:
            continue
        name = _extract_match_name(match)
        if not name:
            continue

        date_part = utc[:10]
        base_id = f"{id_prefix}-{date_part}-{slugify(name)}"
        weekend = _extract_round_label(match) or date_part

        events.append({
            "id": assign_id(base_id),
            "weekend": weekend,
            "name": name,
            "utc": utc,
        })

    events.sort(key=lambda x: x["utc"])
    return events


def scrape_competition(
    competition_id: int,
    date_from: str,
    date_to: str,
    output_dir: Path,
    filename: str,
    min_events: int = 20,
) -> bool:
    if competition_id not in COMPETITION_MAP:
        print(f"ERROR: competition_id {competition_id} not in COMPETITION_MAP", file=sys.stderr)
        return False

    sport_key, league_name, id_prefix = COMPETITION_MAP[competition_id]
    print(f"Fetching {league_name} (id={competition_id}) {date_from}->{date_to}...", file=sys.stderr)

    matches = fetch_matches(competition_id, date_from, date_to)
    print(f"  Got {len(matches)} matches", file=sys.stderr)

    events = build_events_from_matches(matches, id_prefix)

    if len(events) < min_events:
        print(
            f"  Only {len(events)} events (min {min_events}). Checking cache or skipping overwrite.",
            file=sys.stderr,
        )
        return False

    output_path = output_dir / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "sportKey": sport_key,
        "leagueName": league_name,
        "windowFrom": date_from.replace("-", ""),
        "windowTo": date_to.replace("-", ""),
        "events": events,
    }
    output_path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"  Wrote {len(events)} events -> {output_path}", file=sys.stderr)
    return True
