#!/usr/bin/env python3
"""
Scrapes any set of ESPN basketball league slugs using the same Core API
approach as nba.py (see espn_core_api_common.py), but takes slugs as
input instead of one script per league - same pattern as
soccer_generic.py.

Uses a rolling date window (today - PAST_DAYS to today + FUTURE_DAYS)
rather than a fixed season, since college basketball, WNBA, and G League
don't all run on the NBA's Oct-June calendar. Fails soft per-league: an
empty or broken league is logged and skipped, not aborted-with-exit-1,
so one dead slug in a batch doesn't take the others down with it. Only
exits non-zero if the entire batch produced nothing.

Output: basketball/espn-all/<slug>.json, one file per league - separate
from nba.py's own full-season basketball/nba/<year>.json.

Usage:
  python scripts/basketball_generic.py wnba,mens-college-basketball
  SPORT_LEAGUE_SLUGS=wnba,mens-college-basketball python scripts/basketball_generic.py
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from espn_core_api_common import build_events, fetch_league_name  # noqa: E402

SPORT = "basketball"
PAST_DAYS = 14
FUTURE_DAYS = 270  # ~9 months forward - covers a full season for most leagues
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "basketball" / "espn-all"
MIN_EVENTS_TO_WRITE = 1  # below this, treat as "nothing currently scheduled" and skip (not an error)


def get_slugs() -> list[str]:
    if len(sys.argv) > 1:
        raw = sys.argv[1]
    else:
        raw = os.environ.get("SPORT_LEAGUE_SLUGS", "")
    slugs = [s.strip() for s in raw.split(",") if s.strip()]
    if not slugs:
        print("ERROR: no slugs given. Pass as an argument or SPORT_LEAGUE_SLUGS env var.", file=sys.stderr)
        sys.exit(2)
    return slugs


def main():
    slugs = get_slugs()
    today = datetime.now(timezone.utc).date()
    date_from = (today - timedelta(days=PAST_DAYS)).strftime("%Y%m%d")
    date_to = (today + timedelta(days=FUTURE_DAYS)).strftime("%Y%m%d")

    print(f"Scraping {len(slugs)} league(s), window {date_from}-{date_to}: {', '.join(slugs)}", file=sys.stderr)

    written = 0
    empty = 0
    errored = 0

    for slug in slugs:
        print(f"--- {slug} ---", file=sys.stderr)
        try:
            events = build_events(
                sport=SPORT,
                league_slug=slug,
                id_prefix=slug,
                sport_key=f"basketball-{slug}",
                date_from=date_from,
                date_to=date_to,
                round_prefix="Week",
            )
        except Exception as err:  # noqa: BLE001 - one bad league must not kill the batch
            print(f"  ERROR: {slug} raised {err!r}, skipping.", file=sys.stderr)
            errored += 1
            continue

        if len(events) < MIN_EVENTS_TO_WRITE:
            print(f"  {slug}: 0 events in window, skipping (nothing currently scheduled).", file=sys.stderr)
            empty += 1
            continue

        league_name = fetch_league_name(SPORT, slug)

        output_path = OUTPUT_DIR / f"{slug}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps({
            "sportKey": f"basketball-{slug}",
            "leagueName": league_name,
            "windowFrom": date_from,
            "windowTo": date_to,
            "events": events,
        }, indent=2) + "\n")
        print(f"  {slug}: wrote {len(events)} events ({league_name!r}) to {output_path}", file=sys.stderr)
        written += 1

    print(
        f"\nBatch summary: {written} written, {empty} empty/skipped, {errored} errored "
        f"(of {len(slugs)} total).",
        file=sys.stderr,
    )
    if written == 0 and empty == 0:
        print("ERROR: entire batch failed with no successful fetches. Aborting.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
