#!/usr/bin/env python3
"""
MLS (Major League Soccer) schedule scraper for the sportocal-data repo.
See espn_soccer_common.py for the shared ESPN Core API fetching logic
and its caveats.

Unlike the European leagues, MLS runs within a single calendar year
(Feb-Dec, playoffs included), so this uses a plain "YYYY" season label
and date range instead of the "YYYY-YY" cross-year format.

Run this from the repo root: python scripts/mls.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from espn_soccer_common import run_league_scraper  # noqa: E402

today = date.today()
# MLS's season effectively starts in February; if we're in Jan, we're
# still closing out the previous season.
SEASON_YEAR = today.year if today.month >= 2 else today.year - 1
DATE_FROM = f"{SEASON_YEAR}0201"
DATE_TO = f"{SEASON_YEAR}1215"

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "football" / "mls" / f"{SEASON_YEAR}.json"

if __name__ == "__main__":
    run_league_scraper(
        league_slug="usa.1",
        id_prefix="mls",
        sport_key="mls",
        season_label=str(SEASON_YEAR),
        output_path=OUTPUT_PATH,
        date_from=DATE_FROM,
        date_to=DATE_TO,
        round_prefix="Matchweek",
        min_events=80,
    )
