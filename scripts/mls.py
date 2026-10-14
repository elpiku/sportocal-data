#!/usr/bin/env python3
"""MLS scraper — football-data.org (competition id 2145). Requires FOOTBALL_DATA_KEY."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from football_data_common import scrape_competition  # noqa: E402

today = date.today()
# MLS runs Feb–Nov of the same year
SEASON_YEAR = today.year
DATE_FROM = f"{SEASON_YEAR}-02-01"
DATE_TO   = f"{SEASON_YEAR}-11-30"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "football" / "mls"
FILENAME   = f"{SEASON_YEAR}.json"

if __name__ == "__main__":
    scrape_competition(2145, DATE_FROM, DATE_TO, OUTPUT_DIR, FILENAME, min_events=50)
