#!/usr/bin/env python3
"""
Scrapes any set of ESPN soccer competition slugs using the same Core API
approach as premier_league.py etc. (see espn_soccer_common.py), but:

  - takes slugs as input instead of one script per league, so it can
    cover ESPN's full catalog (250+ competitions) without 250 hand-written
    scripts
  - uses a rolling date window (today - PAST_DAYS to today + FUTURE_DAYS)
    instead of a fixed season, since most of ESPN's catalog doesn't run
    on the Aug-June domestic-league calendar the curated scripts assume -
    cups, qualifiers, and international windows don't have a "season" in
    that sense
  - fails soft per-league: an empty or broken competition is logged and
    skipped, not aborted-with-exit-1, so one dead slug in a batch of 15
    doesn't take the other 14 down with it. Only exits non-zero if the
    entire batch produced nothing, which is a signal something systemic
    broke (e.g. the same IP-block problem the Site API had).
  - writes each competition's real ESPN name into its own output file
    (one extra request per competition that actually has events - see
    fetch_league_name in espn_core_api_common.py) so a consumer (e.g.
    this repo's Kotlin app) can read the display name straight out of
    the JSON instead of needing a separately maintained name list.

Output: football/espn-all/<slug>.json, one file per competition, each
holding whatever's currently in the rolling window. This is a different
shape from the curated scripts' full-season files by design - see
module docstring above.

Usage:
  python scripts/soccer_generic.py eng.1,esp.1,ita.1
  SOCCER_LEAGUE_SLUGS=eng.1,esp.1 python scripts/soccer_generic.py
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from espn_soccer_common import build_events, fetch_league_name  # noqa: E402

PAST_DAYS = 14
FUTURE_DAYS = 270  # ~9 months forward - covers a full season for most competitions
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "football" / "espn-all"
MIN_EVENTS_TO_WRITE = 1  # below this, treat as "nothing currently scheduled" and skip (not an error)


def get_slugs() -> list[str]:
    if len(sys.argv) > 1:
        raw = sys.argv[1]
    else:
        raw = os.environ.get("SOCCER_LEAGUE_SLUGS", "")
    slugs = [s.strip() for s in raw.split(",") if s.strip()]
    if not slugs:
        print("ERROR: no slugs given. Pass as an argument or SOCCER_LEAGUE_SLUGS env var.", file=sys.stderr)
        sys.exit(2)
    return slugs


def main():
    slugs = get_slugs()
    today = datetime.now(timezone.utc).date()
    date_from = (today - timedelta(days=PAST_DAYS)).strftime("%Y%m%d")
    date_to = (today + timedelta(days=FUTURE_DAYS)).strftime("%Y%m%d")

    print(f"Scraping {len(slugs)} competition(s), window {date_from}-{date_to}: {', '.join(slugs)}", file=sys.stderr)

    written = 0
    empty = 0
    errored = 0

    for slug in slugs:
        print(f"--- {slug} ---", file=sys.stderr)
        try:
            events = build_events(
                league_slug=slug,
                id_prefix=slug,
                sport_key=f"soccer-{slug}",
                date_from=date_from,
                date_to=date_to,
            )
        except Exception as err:  # noqa: BLE001 - one bad competition must not kill the batch
            print(f"  ERROR: {slug} raised {err!r}, skipping.", file=sys.stderr)
            errored += 1
            continue

        if len(events) < MIN_EVENTS_TO_WRITE:
            print(f"  {slug}: 0 events in window, skipping (nothing currently scheduled).", file=sys.stderr)
            empty += 1
            continue

        # Only fetch the real name for competitions that actually have
        # something to write - no point spending a request on a league
        # that's about to be skipped as empty anyway.
        league_name = fetch_league_name(slug)

        output_path = OUTPUT_DIR / f"{slug}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps({
            "sportKey": f"soccer-{slug}",
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
        # Every single slug in this batch errored out - that's the systemic-failure
        # signal (e.g. IP block), not "these happen to be quiet competitions".
        print("ERROR: entire batch failed with no successful fetches. Aborting.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
