#!/usr/bin/env python3
"""
Premier League schedule scraper for the sportocal-data repo.
See espn_soccer_common.py for the shared ESPN Core API fetching logic
and its caveats.

Run this from the repo root: python scripts/premier_league.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from espn_soccer_common import run_league_scraper  # noqa: E402

# European domestic leagues run Aug(year) - May/June(year+1); this always
# targets the season currently underway (or about to start) relative to
# today, rather than a hardcoded year.
today = date.today()
SEASON_START_YEAR = today.year if today.month >= 7 else today.year - 1
SEASON_LABEL = f"{SEASON_START_YEAR}-{str(SEASON_START_YEAR + 1)[-2:]}"
DATE_FROM = f"{SEASON_START_YEAR}0701"
DATE_TO = f"{SEASON_START_YEAR + 1}0630"

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "football" / "premierleague" / f"{SEASON_START_YEAR + 1}.json"

if __name__ == "__main__":
    run_league_scraper(
        league_slug="eng.1",
        id_prefix="pl",
        sport_key="premierleague",
        season_label=SEASON_LABEL,
        output_path=OUTPUT_PATH,
        date_from=DATE_FROM,
        date_to=DATE_TO,
        round_prefix="Matchweek",
        min_events=100,  # a full 38-matchweek EPL season has 380 games
    )
