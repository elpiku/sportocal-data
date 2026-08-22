#!/usr/bin/env python3
"""
UEFA Champions League schedule scraper for the sportocal-data repo.
See espn_soccer_common.py for the shared ESPN Core API fetching logic
and its caveats.

Note: Champions League doesn't play in numbered "matchweeks" the way
domestic leagues do - it has league-phase matchdays followed by named
knockout rounds (Round of 16, Quarter-finals, ...). extract_weekend_label
falls back through a few plausible ESPN fields for this; if none of them
carry a usable label for this competition specifically, weekend ends up
being just the match date, which isn't wrong, just less descriptive than
ideal.

Run this from the repo root: python scripts/champions_league.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from espn_soccer_common import run_league_scraper  # noqa: E402

today = date.today()
SEASON_START_YEAR = today.year if today.month >= 7 else today.year - 1
SEASON_LABEL = f"{SEASON_START_YEAR}-{str(SEASON_START_YEAR + 1)[-2:]}"
DATE_FROM = f"{SEASON_START_YEAR}0801"
DATE_TO = f"{SEASON_START_YEAR + 1}0601"

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "football" / "championsleague" / f"{SEASON_START_YEAR + 1}.json"

if __name__ == "__main__":
    run_league_scraper(
        league_slug="uefa.champions",
        id_prefix="ucl",
        sport_key="championsleague",
        season_label=SEASON_LABEL,
        output_path=OUTPUT_PATH,
        date_from=DATE_FROM,
        date_to=DATE_TO,
        round_prefix="Matchday",
        min_events=20,
    )
