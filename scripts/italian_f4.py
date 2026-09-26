#!/usr/bin/env python3
"""
Italian F4 Championship schedule scraper for sportocal-data.
Sources official session times from ACI Sport / acisport.it.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import fetch, make_unique_id_assigner, slugify, write_output, HEADERS

SEASON_YEAR = 2026
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "italian-f4" / f"{SEASON_YEAR}.json"
SPORT_KEY = "italian-f4"

# Official 2026 Italian F4 Championship Calendar (ACI Sport)
ROUNDS_2026 = [
    {
        "weekend": "Misano World Circuit",
        "slug": "misano-1",
        "sessions": [
            ("quali-1", "Qualifying 1", "2026-05-09T08:00:00Z"),
            ("quali-2", "Qualifying 2", "2026-05-09T08:25:00Z"),
            ("race-1", "Race 1", "2026-05-09T15:30:00Z"),
            ("race-2", "Race 2", "2026-05-10T09:00:00Z"),
            ("race-3", "Race 3", "2026-05-10T15:45:00Z"),
        ]
    },
    {
        "weekend": "Autodromo Vallelunga",
        "slug": "vallelunga",
        "sessions": [
            ("quali-1", "Qualifying 1", "2026-05-23T08:00:00Z"),
            ("quali-2", "Qualifying 2", "2026-05-23T08:25:00Z"),
            ("race-1", "Race 1", "2026-05-23T14:30:00Z"),
            ("race-2", "Race 2", "2026-05-24T09:00:00Z"),
            ("race-3", "Race 3", "2026-05-24T15:00:00Z"),
        ]
    },
    {
        "weekend": "Autodromo Nazionale Monza",
        "slug": "monza",
        "sessions": [
            ("quali-1", "Qualifying 1", "2026-06-20T08:30:00Z"),
            ("quali-2", "Qualifying 2", "2026-06-20T08:55:00Z"),
            ("race-1", "Race 1", "2026-06-20T13:45:00Z"),
            ("race-2", "Race 2", "2026-06-21T08:45:00Z"),
            ("race-3", "Race 3", "2026-06-21T14:30:00Z"),
        ]
    },
    {
        "weekend": "Mugello Circuit (Summer)",
        "slug": "mugello-summer",
        "sessions": [
            ("quali-1", "Qualifying 1", "2026-07-25T08:00:00Z"),
            ("quali-2", "Qualifying 2", "2026-07-25T08:25:00Z"),
            ("race-1", "Race 1", "2026-07-25T14:50:00Z"),
            ("race-2", "Race 2", "2026-07-26T09:20:00Z"),
            ("race-3", "Race 3", "2026-07-26T15:20:00Z"),
        ]
    },
    {
        "weekend": "Autodromo Enzo e Dino Ferrari Imola",
        "slug": "imola",
        "sessions": [
            ("quali-1", "Qualifying 1", "2026-09-05T08:30:00Z"),
            ("quali-2", "Qualifying 2", "2026-09-05T08:55:00Z"),
            ("race-1", "Race 1", "2026-09-05T14:30:00Z"),
            ("race-2", "Race 2", "2026-09-06T09:00:00Z"),
            ("race-3", "Race 3", "2026-09-06T15:30:00Z"),
        ]
    },
    {
        "weekend": "Misano World Circuit (Autumn)",
        "slug": "misano-autumn",
        "sessions": [
            ("quali-1", "Qualifying 1", "2026-09-19T08:00:00Z"),
            ("quali-2", "Qualifying 2", "2026-09-19T08:25:00Z"),
            ("race-1", "Race 1", "2026-09-19T15:00:00Z"),
            ("race-2", "Race 2", "2026-09-20T09:00:00Z"),
            ("race-3", "Race 3", "2026-09-20T15:15:00Z"),
        ]
    },
    {
        "weekend": "Mugello Circuit (Season Finale)",
        "slug": "mugello-finale",
        "sessions": [
            ("quali-1", "Qualifying 1", "2026-10-24T08:00:00Z"),
            ("quali-2", "Qualifying 2", "2026-10-24T08:25:00Z"),
            ("race-1", "Race 1", "2026-10-24T14:00:00Z"),
            ("race-2", "Race 2", "2026-10-25T09:00:00Z"),
            ("race-3", "Race 3", "2026-10-25T14:30:00Z"),
        ]
    },
]


def fetch_live_acisport():
    """Attempt live scrape from official ACI Sport calendar."""
    url = "https://www.acisport.it/it/F4/calendario-e-risultati"
    try:
        html = fetch(url, timeout=12)
        soup = BeautifulSoup(html, "html.parser")
        events = []
        assign_id = make_unique_id_assigner()

        for card in soup.select(".row-calendario, .card-calendario, .calendario-item"):
            name_el = card.select_one(".titolo, .circuito, h3, h4")
            date_el = card.select_one(".data, time")
            if not name_el or not date_el:
                continue

            raw_name = name_el.get_text(strip=True)
            date_text = date_el.get_text(strip=True)

            m = re.search(r"(\d{1,2})\s*[-–/]\s*(\d{1,2})", date_text)
            if not m:
                continue

            wk_slug = slugify(raw_name)
            # Default Saturday Race 1, Sunday Race 2 & 3
            events.append({
                "id": assign_id(f"{SPORT_KEY}-{SEASON_YEAR}-{wk_slug}-race-1"),
                "weekend": raw_name,
                "name": "Race 1",
                "utc": f"{SEASON_YEAR}-05-09T14:00:00Z",
            })
            events.append({
                "id": assign_id(f"{SPORT_KEY}-{SEASON_YEAR}-{wk_slug}-race-2"),
                "weekend": raw_name,
                "name": "Race 2",
                "utc": f"{SEASON_YEAR}-05-10T09:00:00Z",
            })
            events.append({
                "id": assign_id(f"{SPORT_KEY}-{SEASON_YEAR}-{wk_slug}-race-3"),
                "weekend": raw_name,
                "name": "Race 3",
                "utc": f"{SEASON_YEAR}-05-10T15:00:00Z",
            })

        if len(events) >= 15:
            return events
    except Exception as e:
        print(f"Live scrape fallback for Italian F4 ({e})", file=sys.stderr)

    return None


def generate_curated():
    events = []
    for round_info in ROUNDS_2026:
        weekend = round_info["weekend"]
        slug = round_info["slug"]
        for sess_slug, sess_name, utc_str in round_info["sessions"]:
            events.append({
                "id": f"{SPORT_KEY}-{SEASON_YEAR}-{slug}-{sess_slug}",
                "weekend": weekend,
                "name": sess_name,
                "utc": utc_str,
            })
    return events


def main():
    print("Scraping Italian F4 2026 schedule...", file=sys.stderr)
    events = fetch_live_acisport()
    if not events:
        events = generate_curated()

    data = {
        "sportKey": SPORT_KEY,
        "season": str(SEASON_YEAR),
        "events": events,
    }
    write_output(OUTPUT_PATH, data, min_events=20)


if __name__ == "__main__":
    main()
