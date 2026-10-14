#!/usr/bin/env python3
"""La Liga scraper — football-data.org (competition id 2014). Requires FOOTBALL_DATA_KEY."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from football_data_common import scrape_competition  # noqa: E402

today = date.today()
SEASON_START_YEAR = today.year if today.month >= 7 else today.year - 1
DATE_FROM = f"{SEASON_START_YEAR}-07-01"
DATE_TO   = f"{SEASON_START_YEAR + 1}-06-30"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "football" / "laliga"
FILENAME   = f"{SEASON_START_YEAR + 1}.json"

if __name__ == "__main__":
    scrape_competition(2014, DATE_FROM, DATE_TO, OUTPUT_DIR, FILENAME, min_events=100)
