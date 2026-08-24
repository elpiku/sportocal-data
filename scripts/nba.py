#!/usr/bin/env python3
"""
NBA schedule scraper for the sportocal-data repo.
See espn_core_api_common.py for the shared ESPN Core API fetching logic
and its caveats (why sports.core.api.espn.com and not site.api.espn.com).

Run this from the repo root: python scripts/nba.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from espn_core_api_common import run_league_scraper  # noqa: E402

# NBA season runs Oct(year) - Jun(year+1) (preseason in Oct, Finals typically
# wrap by mid-June). Targets the season currently underway/about to start
# relative to today, same pattern as the soccer scripts.
today = date.today()
SEASON_START_YEAR = today.year if today.month >= 8 else today.year - 1
SEASON_LABEL = f"{SEASON_START_YEAR}-{str(SEASON_START_YEAR + 1)[-2:]}"
DATE_FROM = f"{SEASON_START_YEAR}1001"
DATE_TO = f"{SEASON_START_YEAR + 1}0630"

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "basketball" / "nba" / f"{SEASON_START_YEAR + 1}.json"

if __name__ == "__main__":
    run_league_scraper(
        sport="basketball",
        league_slug="nba",
        id_prefix="nba",
        sport_key="nba",
        season_label=SEASON_LABEL,
        output_path=OUTPUT_PATH,
        date_from=DATE_FROM,
        date_to=DATE_TO,
        round_prefix="Week",
        min_events=800,  # 82-game x 30-team regular season alone is 1230 games; playoffs add more
    )
