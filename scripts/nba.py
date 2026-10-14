#!/usr/bin/env python3
"""
NBA schedule scraper - powered by BALLDONTLIE.
Requires env var: BALLDONTLIE_KEY

Run from repo root: python scripts/nba.py
Output: basketball/nba/<year>.json
"""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from balldontlie_common import fetch_nba_games, build_nba_events  # noqa: E402

today = date.today()
# NBA season Oct(year) – Jun(year+1)
SEASON_START_YEAR = today.year if today.month >= 8 else today.year - 1
SEASON_LABEL = f"{SEASON_START_YEAR}-{str(SEASON_START_YEAR + 1)[-2:]}"
DATE_FROM = f"{SEASON_START_YEAR}-10-01"
DATE_TO   = f"{SEASON_START_YEAR + 1}-06-30"

OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "basketball" / "nba" / f"{SEASON_START_YEAR + 1}.json"
)

if __name__ == "__main__":
    print(f"Fetching NBA {SEASON_LABEL} ({DATE_FROM} → {DATE_TO})…", file=sys.stderr)
    games  = fetch_nba_games(DATE_FROM, DATE_TO)
    events = build_nba_events(games, id_prefix="nba")
    print(f"Got {len(events)} games.", file=sys.stderr)

    if len(events) < 800:
        print(
            f"WARNING: only {len(events)} events (expected 1230+ for full season). "
            "Not writing to avoid overwriting good data.",
            file=sys.stderr,
        )
        sys.exit(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "sportKey": "nba",
        "leagueName": "NBA",
        "season": SEASON_LABEL,
        "events": events,
    }
    OUTPUT_PATH.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Wrote {len(events)} events → {OUTPUT_PATH}", file=sys.stderr)
