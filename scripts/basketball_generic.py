#!/usr/bin/env python3
"""
Basketball generic scraper — API-Sports basketball API.
Covers WNBA, FIBA, NBL, college basketball, and other leagues.
(NBA is handled separately by nba.py via BALLDONTLIE.)

Requires env var: API_SPORTS_KEY
Output: basketball/api-sports/<slug>.json
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

PAST_DAYS  = 14
FUTURE_DAYS = 270
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "basketball" / "api-sports"
MIN_EVENTS = 5

# API-Sports basketball league IDs
# https://www.api-sports.io/documentation/basketball/v1#tag/leagues
TARGET_LEAGUES: dict[int, tuple[str, str]] = {
    12:  ("basketball-wnba",            "WNBA"),
    116: ("basketball-nba-g-league",    "NBA G League"),
    117: ("basketball-college-men",     "NCAA Men's Basketball"),
    118: ("basketball-college-women",   "NCAA Women's Basketball"),
    29:  ("basketball-fiba",            "FIBA Basketball World Cup"),
    28:  ("basketball-fiba-americas",   "FIBA AmeriCup"),
    27:  ("basketball-fiba-eurobasket", "FIBA EuroBasket"),
    131: ("basketball-nbl",             "NBL (Australia)"),
    # EuroLeague
    120: ("basketball-euroleague",      "EuroLeague"),
    121: ("basketball-eurocup",         "EuroCup"),
}


def main():
    today       = datetime.now(timezone.utc).date()
    date_from   = (today - timedelta(days=PAST_DAYS)).strftime("%Y-%m-%d")
    date_to     = (today + timedelta(days=FUTURE_DAYS)).strftime("%Y-%m-%d")
    date_from_s = (today - timedelta(days=PAST_DAYS)).strftime("%Y%m%d")
    date_to_s   = (today + timedelta(days=FUTURE_DAYS)).strftime("%Y%m%d")

    # API-Sports basketball uses a single season year or "yyyy-yyyy"
    season = today.year if today.month >= 8 else today.year - 1

    client  = ApiSportsClient("basketball")
    written = skipped = 0

    # Allow running a specific subset from env or CLI
    env_ids = os.environ.get("BBALL_LEAGUE_IDS", "")
    if env_ids:
        ids = [int(i.strip()) for i in env_ids.split(",") if i.strip().isdigit()]
        targets = {k: TARGET_LEAGUES[k] for k in ids if k in TARGET_LEAGUES}
    else:
        targets = TARGET_LEAGUES

    for league_id, (sport_key, league_name) in targets.items():
        slug = sport_key.replace("basketball-", "")
        print(f"Fetching {league_name} (id={league_id})…", file=sys.stderr)
        try:
            # API-Sports basketball uses /games not /fixtures
            data = client._get("games", {"league": league_id, "season": season,
                                          "from": date_from, "to": date_to})
            fixtures = (data or {}).get("response", [])
        except Exception as err:
            print(f"  ERROR: {err!r}", file=sys.stderr)
            skipped += 1
            continue

        # Normalise game → fixture-like shape for build_events_from_fixtures
        normalised = []
        for g in fixtures:
            normalised.append({
                "teams": g.get("teams"),
                "fixture": {"date": (g.get("date") or {}).get("start")},
                "league":  {"round": g.get("week")},
            })

        events = build_events_from_fixtures(normalised, id_prefix=slug, sport_key=sport_key)
        output_path = OUTPUT_DIR / f"{slug}.json"
        ok = write_league_file(
            output_path, sport_key, league_name, date_from_s, date_to_s, events, MIN_EVENTS
        )
        if ok:
            written += 1
        else:
            skipped += 1

    print(f"\nDone: {written} written, {skipped} skipped.", file=sys.stderr)


if __name__ == "__main__":
    main()
