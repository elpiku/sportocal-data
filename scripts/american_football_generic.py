#!/usr/bin/env python3
"""
American football generic scraper — API-Sports american-football API.
Covers NFL, NCAA College Football.

Requires env var: API_SPORTS_KEY
Output: american-football/api-sports/<slug>.json
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_sports_common import ApiSportsClient, build_events_from_fixtures, write_league_file  # noqa: E402

PAST_DAYS   = 14
FUTURE_DAYS = 270
OUTPUT_DIR  = Path(__file__).resolve().parent.parent / "american-football" / "api-sports"
MIN_EVENTS  = 5

# API-Sports american-football league IDs
TARGET_LEAGUES: dict[int, tuple[str, str]] = {
    1:   ("american-football-nfl",            "National Football League"),
    2:   ("american-football-college-football","NCAA College Football"),
    3:   ("american-football-cfl",            "Canadian Football League"),
}


def main():
    today       = datetime.now(timezone.utc).date()
    date_from   = (today - timedelta(days=PAST_DAYS)).strftime("%Y-%m-%d")
    date_to     = (today + timedelta(days=FUTURE_DAYS)).strftime("%Y-%m-%d")
    date_from_s = date_from.replace("-", "")
    date_to_s   = date_to.replace("-", "")
    season = today.year if today.month >= 7 else today.year - 1

    client  = ApiSportsClient("american-football")
    written = skipped = 0

    env_ids = os.environ.get("AMFOOTBALL_LEAGUE_IDS", "")
    targets = (
        {int(i): TARGET_LEAGUES[int(i)] for i in env_ids.split(",")
         if i.strip().isdigit() and int(i) in TARGET_LEAGUES}
        if env_ids else TARGET_LEAGUES
    )

    for league_id, (sport_key, league_name) in targets.items():
        slug = sport_key.replace("american-football-", "")
        print(f"Fetching {league_name} (id={league_id})…", file=sys.stderr)
        try:
            data = client._get("games", {"league": league_id, "season": season})
            fixtures = (data or {}).get("response", [])
        except Exception as err:
            print(f"  ERROR: {err!r}", file=sys.stderr); skipped += 1; continue

        normalised = [{
            "teams":   g.get("teams"),
            "fixture": {"date": (g.get("game") or {}).get("date", {}).get("date")},
            "league":  {"round": (g.get("game") or {}).get("week")},
        } for g in fixtures]

        events = build_events_from_fixtures(normalised, slug, sport_key)
        ok = write_league_file(OUTPUT_DIR / f"{slug}.json", sport_key, league_name,
                               date_from_s, date_to_s, events, MIN_EVENTS)
        written += ok; skipped += not ok

    print(f"\nDone: {written} written, {skipped} skipped.", file=sys.stderr)


if __name__ == "__main__":
    main()
