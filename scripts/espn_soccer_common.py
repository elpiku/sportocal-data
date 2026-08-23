#!/usr/bin/env python3
"""
Soccer-specific wrapper around espn_core_api_common.py, used by
premier_league.py, champions_league.py, la_liga.py, serie_a.py,
bundesliga.py, and mls.py. All the actual fetch/parse logic now lives
in espn_core_api_common.py (sport-agnostic, shared with basketball and
whatever's added after it) - this module just pins sport="soccer" and
keeps the original function signatures so none of those six scripts
needed to change.

See espn_core_api_common.py's docstring for why this uses
sports.core.api.espn.com rather than site.api.espn.com.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from espn_core_api_common import build_events as _build_events  # noqa: E402
from espn_core_api_common import run_league_scraper as _run_league_scraper  # noqa: E402
from espn_core_api_common import (  # noqa: E402,F401
    to_utc_iso,
    extract_teams,
    extract_weekend_label,
    fetch_event_refs as _fetch_event_refs,
    fetch_event,
    fetch_league_name as _fetch_league_name,
)

SPORT = "soccer"


def fetch_event_refs(league_slug: str, date_from: str, date_to: str):
    return _fetch_event_refs(SPORT, league_slug, date_from, date_to)


def fetch_league_name(league_slug: str) -> str:
    return _fetch_league_name(SPORT, league_slug)


def build_events(
    league_slug: str,
    id_prefix: str,
    sport_key: str,
    date_from: str,
    date_to: str,
    round_prefix: str = "Matchweek",
):
    return _build_events(SPORT, league_slug, id_prefix, sport_key, date_from, date_to, round_prefix)


def run_league_scraper(
    league_slug: str,
    id_prefix: str,
    sport_key: str,
    season_label: str,
    output_path: Path,
    date_from: str,
    date_to: str,
    round_prefix: str = "Matchweek",
    min_events: int = 20,
):
    return _run_league_scraper(
        SPORT, league_slug, id_prefix, sport_key, season_label,
        output_path, date_from, date_to, round_prefix, min_events,
    )
