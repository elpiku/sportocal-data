#!/usr/bin/env python3
"""
Targeted Lacrosse Scraper for sportocal-data.
Fetches PLL, NLL, and NCAA Men's & Women's Lacrosse.
Outputs to lacrosse/espn-all/<slug>.json.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from espn_core_api_common import build_events, fetch_league_name  # noqa: E402

SPORT = "lacrosse"
PAST_DAYS = 14
FUTURE_DAYS = 270
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "lacrosse" / "espn-all"
MIN_EVENTS_THRESHOLD = 3

TARGET_LEAGUES = {
    "pll": "Premier Lacrosse League (PLL)",
    "nll": "National Lacrosse League (NLL)",
    "mens-college-lacrosse": "NCAA Men's Lacrosse",
    "womens-college-lacrosse": "NCAA Women's Lacrosse",
}


def main():
    today = datetime.now(timezone.utc).date()
    date_from = (today - timedelta(days=PAST_DAYS)).strftime("%Y%m%d")
    date_to = (today + timedelta(days=FUTURE_DAYS)).strftime("%Y%m%d")

    print(f"Scraping {len(TARGET_LEAGUES)} targeted lacrosse leagues ({date_from} to {date_to})...", file=sys.stderr)
    written, skipped = 0, 0

    for slug, preferred_name in TARGET_LEAGUES.items():
        print(f"Fetching: {preferred_name} [{slug}]", file=sys.stderr)
        try:
            events = build_events(
                sport=SPORT,
                league_slug=slug,
                id_prefix=f"lacrosse-{slug}",
                sport_key=f"lacrosse-{slug}",
                date_from=date_from,
                date_to=date_to,
                round_prefix="Game",
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
                    "sportKey": f"lacrosse-{slug}",
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
