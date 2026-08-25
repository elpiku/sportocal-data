#!/usr/bin/env python3
"""
Targeted Cricket Scraper for sportocal-data.
Fetches IPL, ICC World Cup, T20 World Cup, BBL, The Hundred, CPL, PSL.
Outputs to cricket/espn-all/<slug>.json.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from espn_core_api_common import build_events, fetch_league_name  # noqa: E402

SPORT = "cricket"
PAST_DAYS = 14
FUTURE_DAYS = 270
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "cricket" / "espn-all"
MIN_EVENTS_THRESHOLD = 3

TARGET_LEAGUES = {
    # Top Franchise Leagues
    "ipl": "Indian Premier League (IPL)",
    "big-bash-league": "Big Bash League (BBL)",
    "the-hundred": "The Hundred",
    "caribbean-premier-league": "Caribbean Premier League (CPL)",
    "pakistan-super-league": "Pakistan Super League (PSL)",

    # Major ICC Tournaments
    "icc-cricket-world-cup": "ICC Cricket World Cup",
    "icc-mens-t20-world-cup": "ICC Men's T20 World Cup",
    "icc-champions-trophy": "ICC Champions Trophy",
}

BLOCKED_KEYWORDS = ("warmup", "warm_up", "warm-up", ".u19")


def is_valid_slug(slug: str) -> bool:
    if slug not in TARGET_LEAGUES:
        return False
    return not any(kw in slug.lower() for kw in BLOCKED_KEYWORDS)


def main():
    today = datetime.now(timezone.utc).date()
    date_from = (today - timedelta(days=PAST_DAYS)).strftime("%Y%m%d")
    date_to = (today + timedelta(days=FUTURE_DAYS)).strftime("%Y%m%d")

    print(f"Scraping {len(TARGET_LEAGUES)} targeted cricket competitions ({date_from} to {date_to})...", file=sys.stderr)
    written, skipped = 0, 0

    for slug, preferred_name in TARGET_LEAGUES.items():
        if not is_valid_slug(slug):
            continue

        print(f"Fetching: {preferred_name} [{slug}]", file=sys.stderr)
        try:
            events = build_events(
                sport=SPORT,
                league_slug=slug,
                id_prefix=f"cricket-{slug}",
                sport_key=f"cricket-{slug}",
                date_from=date_from,
                date_to=date_to,
                round_prefix="Match",
            )
        except Exception as err:
            print(f"  ERROR: {slug} failed ({err!r}), skipping.", file=sys.stderr)
            continue

        if len(events) < MIN_EVENTS_THRESHOLD:
            print(f"  {slug}: only {len(events)} events, skipping.", file=sys.stderr)
            skipped += 1
            continue

        league_name = fetch_league_name(SPORT, slug)
        display_name = preferred_name if league_name == slug else league_name

        output_path = OUTPUT_DIR / f"{slug}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "sportKey": f"cricket-{slug}",
                    "leagueName": display_name,
                    "windowFrom": date_from,
                    "windowTo": date_to,
                    "events": events,
                },
                indent=2,
            )
            + "\n"
        )
        print(f"  Wrote {len(events)} events to {output_path.name}", file=sys.stderr)
        written += 1

    print(f"\nCompleted: {written} written, {skipped} skipped.", file=sys.stderr)


if __name__ == "__main__":
    main()
