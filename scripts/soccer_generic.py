#!/usr/bin/env python3
"""
Soccer/football generic scraper - powered by API-Sports football API.
Covers Ligue 1, Eredivisie, Liga MX, Brasileirão, Saudi Pro League, and
many more competitions not covered by the curated football-data.org scripts.

Requires env var: API_SPORTS_KEY

Run from repo root: python scripts/soccer_generic.py
Output: football/api-sports/<slug>.json
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_sports_common import (  # noqa: E402
    ApiSportsClient,
    build_events_from_fixtures,
    write_league_file,
)

PAST_DAYS   = 14
FUTURE_DAYS = 270
OUTPUT_DIR  = Path(__file__).resolve().parent.parent / "football" / "api-sports"
MIN_EVENTS  = 5

# league_id (API-Sports) → (sport_key, display_name, season_logic)
# season_logic: "aug" = starts Aug of start_year; "jan" = calendar year
TARGET_LEAGUES: dict[int, tuple[str, str]] = {
    # Tier 1 domestic (not covered by football-data.org curated scripts)
    61:  ("football-ligue1",       "Ligue 1"),
    71:  ("football-brasileirao",  "Brasileirão Série A"),
    262: ("football-ligamx",       "Liga MX"),
    94:  ("football-primeiraliga", "Primeira Liga"),
    88:  ("football-eredivisie",   "Eredivisie"),
    307: ("football-saudi-pro",    "Saudi Pro League"),
    203: ("football-super-lig",    "Süper Lig"),
    128: ("football-arg1",         "Argentine Primera División"),
    179: ("football-scottish-prem","Scottish Premiership"),
    144: ("football-belgian-pro",  "Belgian Pro League"),
    98:  ("football-j1-league",    "J1 League"),
    # Tier 2
    40:  ("football-championship", "EFL Championship"),
    78:  ("football-2bundesliga",  "2. Bundesliga"),
    140: ("football-laliga2",      "LaLiga 2"),
    66:  ("football-ligue2",       "Ligue 2"),
    135: ("football-serieb",       "Serie B"),
    89:  ("football-eerste",       "Eerste Divisie"),
    72:  ("football-serieb-bra",   "Série B (Brazil)"),
    # Major European cups
    3:   ("football-ucl",          "UEFA Champions League"),
    4:   ("football-uel",          "UEFA Europa League"),
    5:   ("football-uecl",         "UEFA Conference League"),
    # Other continental
    13:  ("football-libertadores",  "Copa Libertadores"),
    11:  ("football-sudamericana",  "Copa Sudamericana"),
    12:  ("football-caf-cl",        "CAF Champions League"),
    17:  ("football-afc-cl",        "AFC Champions League"),
    8:   ("football-nations-league","UEFA Nations League"),
    # Domestic cups
    45:  ("football-facup",        "FA Cup"),
    48:  ("football-carabao-cup",  "Carabao Cup"),
    143: ("football-copa-del-rey", "Copa del Rey"),
    137: ("football-coppa-italia", "Coppa Italia"),
    81:  ("football-dfb-pokal",    "DFB-Pokal"),
    # Women
    253: ("football-nwsl",         "NWSL"),
    483: ("football-wsl",          "Barclays Women's Super League"),
}


def current_season(start_month: int = 8) -> int:
    """Return the starting year of the current season."""
    today = datetime.now(timezone.utc).date()
    return today.year if today.month >= start_month else today.year - 1


def main():
    today = datetime.now(timezone.utc).date()
    date_from_dt = today - timedelta(days=PAST_DAYS)
    date_to_dt   = today + timedelta(days=FUTURE_DAYS)
    date_from    = date_from_dt.strftime("%Y-%m-%d")
    date_to      = date_to_dt.strftime("%Y-%m-%d")
    date_from_ym = date_from_dt.strftime("%Y%m%d")
    date_to_ym   = date_to_dt.strftime("%Y%m%d")

    client = ApiSportsClient("football")
    written = skipped = 0
    season = current_season(8)

    for league_id, (sport_key, league_name) in TARGET_LEAGUES.items():
        slug = sport_key.replace("football-", "")
        print(f"Fetching {league_name} (id={league_id}, season={season})…", file=sys.stderr)
        try:
            fixtures = client.get_fixtures_by_date_range(league_id, season, date_from, date_to)
        except Exception as err:
            print(f"  ERROR: {err!r}, skipping.", file=sys.stderr)
            skipped += 1
            continue

        if not fixtures:
            # Try previous season in case current hasn't started yet
            fixtures = client.get_fixtures_by_date_range(league_id, season - 1, date_from, date_to)

        events = build_events_from_fixtures(fixtures, id_prefix=slug, sport_key=sport_key)
        output_path = OUTPUT_DIR / f"{slug}.json"
        ok = write_league_file(
            output_path, sport_key, league_name, date_from_ym, date_to_ym, events, MIN_EVENTS
        )
        if ok:
            written += 1
        else:
            skipped += 1

    print(f"\nDone: {written} written, {skipped} skipped.", file=sys.stderr)


if __name__ == "__main__":
    main()
