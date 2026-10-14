#!/usr/bin/env python3
"""
Handball generic scraper - API-Sports Handball API.
Covers EHF Champions League, Handball Bundesliga, Liga ASOBAL.
Requires env var: API_SPORTS_KEY
Output: handball/api-sports/<slug>.json
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_sports_common import ApiSportsClient, build_events_from_fixtures, write_league_file

PAST_DAYS = 14
FUTURE_DAYS = 270
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "handball" / "api-sports"
MIN_EVENTS = 3

TARGET_LEAGUES: dict[int, tuple[str, str]] = {
    1: ("handball-cl",           "EHF Champions League"),
    6: ("handball-bundesliga",   "Handball-Bundesliga"),
    7: ("handball-asobal",       "Liga ASOBAL"),
    4: ("handball-starligue",    "LNH Division 1"),
}


def main():
    today = datetime.now(timezone.utc).date()
    date_from = (today - timedelta(days=PAST_DAYS)).strftime("%Y-%m-%d")
    date_to = (today + timedelta(days=FUTURE_DAYS)).strftime("%Y-%m-%d")
    date_from_s = date_from.replace("-", "")
    date_to_s = date_to.replace("-", "")
    season = today.year if today.month >= 8 else today.year - 1

    client = ApiSportsClient("handball")
    written = skipped = 0

    for league_id, (sport_key, league_name) in TARGET_LEAGUES.items():
        slug = sport_key.replace("handball-", "")
        print(f"Fetching {league_name}...", file=sys.stderr)
        try:
            data = client._get("games", {"league": league_id, "season": season, "date": date_from})
            fixtures = (data or {}).get("response", [])
        except Exception as err:
            print(f"  ERROR: {err!r}", file=sys.stderr)
            skipped += 1
            continue

        normalised = [
            {
                "teams": g.get("teams"),
                "fixture": {"date": g.get("date")},
                "league": {"round": g.get("week") or league_name},
            }
            for g in fixtures
        ]
        events = build_events_from_fixtures(normalised, slug, sport_key)
        ok = write_league_file(
            OUTPUT_DIR / f"{slug}.json",
            sport_key,
            league_name,
            date_from_s,
            date_to_s,
            events,
            MIN_EVENTS,
        )
        if ok:
            written += 1
        else:
            skipped += 1

    print(f"Done: {written} written, {skipped} skipped.", file=sys.stderr)


if __name__ == "__main__":
    main()
