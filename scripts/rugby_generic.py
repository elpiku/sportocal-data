#!/usr/bin/env python3
"""
Targeted Rugby Scraper for sportocal-data.
Fetches Six Nations, Rugby Championship, Premiership, Champions Cup, Super Rugby, NRL, Super League.
Outputs to rugby/espn-all/<slug>.json.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from espn_core_api_common import build_events, fetch_league_name  # noqa: E402

PAST_DAYS = 14
FUTURE_DAYS = 270
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "rugby" / "espn-all"
MIN_EVENTS_THRESHOLD = 3

# (sport_type, slug) -> Preferred Name
TARGET_LEAGUES = {
    # Rugby Union
    ("rugby", "six-nations"): "Six Nations",
    ("rugby", "rugby-championship"): "The Rugby Championship",
    ("rugby", "premiership-rugby"): "Gallagher Premiership Rugby",
    ("rugby", "european-rugby-champions-cup"): "Investec Champions Cup",
    ("rugby", "super-rugby"): "Super Rugby Pacific",
    ("rugby", "world-cup"): "Rugby World Cup",

    # Rugby League
    ("rugby-league", "nrl"): "NRL (National Rugby League)",
    ("rugby-league", "super-league"): "Betfred Super League",
}

BLOCKED_KEYWORDS = ("friendly", "exhibition", ".u20")


def is_valid_slug(slug: str) -> bool:
    return not any(kw in slug.lower() for kw in BLOCKED_KEYWORDS)


def main():
    today = datetime.now(timezone.utc).date()
    date_from = (today - timedelta(days=PAST_DAYS)).strftime("%Y%m%d")
    date_to = (today + timedelta(days=FUTURE_DAYS)).strftime("%Y%m%d")

    print(f"Scraping {len(TARGET_LEAGUES)} targeted rugby competitions ({date_from} to {date_to})...", file=sys.stderr)
    written, skipped = 0, 0

    for (sport, slug), preferred_name in TARGET_LEAGUES.items():
        if not is_valid_slug(slug):
            continue

        print(f"Fetching: {preferred_name} [{sport}/{slug}]", file=sys.stderr)
        try:
            events = build_events(
                sport=sport,
                league_slug=slug,
                id_prefix=f"rugby-{slug}",
                sport_key=f"rugby-{slug}",
                date_from=date_from,
                date_to=date_to,
                round_prefix="Round",
            )
        except Exception as err:
            print(f"  ERROR: {sport}/{slug} failed ({err!r}), skipping.", file=sys.stderr)
            continue

        if len(events) < MIN_EVENTS_THRESHOLD:
            print(f"  {slug}: only {len(events)} events, skipping.", file=sys.stderr)
            skipped += 1
            continue

        league_name = fetch_league_name(sport, slug)
        display_name = preferred_name if league_name == slug else league_name

        output_path = OUTPUT_DIR / f"{slug}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "sportKey": f"rugby-{slug}",
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
