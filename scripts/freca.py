#!/usr/bin/env python3
"""
Formula Regional European Championship (FRECA) schedule scraper for sportocal-data.
Sources official session times from ACI Sport / formularegionaleubyalpine.com.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import fetch, make_unique_id_assigner, slugify, write_output, HEADERS

SEASON_YEAR = 2026
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "freca" / f"{SEASON_YEAR}.json"
SPORT_KEY = "freca"

# Official 2026 FRECA Championship Calendar
ROUNDS_2026 = [
    {
        "weekend": "Red Bull Ring",
        "slug": "red-bull-ring",
        "sessions": [
            ("quali-1", "Qualifying 1", "2026-04-25T07:30:00Z"),
            ("race-1", "Race 1", "2026-04-25T11:45:00Z"),
            ("quali-2", "Qualifying 2", "2026-04-26T07:15:00Z"),
            ("race-2", "Race 2", "2026-04-26T12:05:00Z"),
        ]
    },
    {
        "weekend": "Circuit Zandvoort",
        "slug": "zandvoort",
        "sessions": [
            ("quali-1", "Qualifying 1", "2026-05-23T07:30:00Z"),
            ("race-1", "Race 1", "2026-05-23T11:45:00Z"),
            ("quali-2", "Qualifying 2", "2026-05-24T07:15:00Z"),
            ("race-2", "Race 2", "2026-05-24T12:05:00Z"),
        ]
    },
    {
        "weekend": "Spa-Francorchamps",
        "slug": "spa",
        "sessions": [
            ("quali-1", "Qualifying 1", "2026-05-30T08:00:00Z"),
            ("race-1", "Race 1", "2026-05-30T12:20:00Z"),
            ("quali-2", "Qualifying 2", "2026-05-31T07:30:00Z"),
            ("race-2", "Race 2", "2026-05-31T13:10:00Z"),
        ]
    },
    {
        "weekend": "Autodromo Nazionale Monza",
        "slug": "monza",
        "sessions": [
            ("quali-1", "Qualifying 1", "2026-06-20T07:30:00Z"),
            ("race-1", "Race 1", "2026-06-20T12:00:00Z"),
            ("quali-2", "Qualifying 2", "2026-06-21T07:30:00Z"),
            ("race-2", "Race 2", "2026-06-21T12:15:00Z"),
        ]
    },
    {
        "weekend": "Hungaroring",
        "slug": "hungaroring",
        "sessions": [
            ("quali-1", "Qualifying 1", "2026-07-04T07:30:00Z"),
            ("race-1", "Race 1", "2026-07-04T11:45:00Z"),
            ("quali-2", "Qualifying 2", "2026-07-05T07:15:00Z"),
            ("race-2", "Race 2", "2026-07-05T12:05:00Z"),
        ]
    },
    {
        "weekend": "Circuit Paul Ricard",
        "slug": "paul-ricard",
        "sessions": [
            ("quali-1", "Qualifying 1", "2026-07-18T07:30:00Z"),
            ("race-1", "Race 1", "2026-07-18T12:00:00Z"),
            ("quali-2", "Qualifying 2", "2026-07-19T07:15:00Z"),
            ("race-2", "Race 2", "2026-07-19T12:10:00Z"),
        ]
    },
    {
        "weekend": "Autodromo Enzo e Dino Ferrari Imola",
        "slug": "imola",
        "sessions": [
            ("quali-1", "Qualifying 1", "2026-09-05T07:30:00Z"),
            ("race-1", "Race 1", "2026-09-05T12:00:00Z"),
            ("quali-2", "Qualifying 2", "2026-09-06T07:15:00Z"),
            ("race-2", "Race 2", "2026-09-06T12:15:00Z"),
        ]
    },
    {
        "weekend": "Hockenheimring",
        "slug": "hockenheimring",
        "sessions": [
            ("quali-1", "Qualifying 1", "2026-09-12T07:30:00Z"),
            ("race-1", "Race 1", "2026-09-12T11:55:00Z"),
            ("quali-2", "Qualifying 2", "2026-09-13T07:15:00Z"),
            ("race-2", "Race 2", "2026-09-13T12:05:00Z"),
        ]
    },
]


def fetch_live_freca():
    """Attempt live scrape from official FRECA calendar portal."""
    url = "https://formularegionaleubyalpine.com/calendar/"
    try:
        html = fetch(url, timeout=12)
        soup = BeautifulSoup(html, "html.parser")
        events = []
        assign_id = make_unique_id_assigner()

        # Look for race calendar event entries
        for item in soup.select(".race-calendar-item, .event-item, article"):
            title_node = item.select_one(".title, h2, h3, a")
            date_node = item.select_one(".date, time")
            if not title_node or not date_node:
                continue

            raw_title = title_node.get_text(strip=True)
            date_text = date_node.get_text(strip=True)

            m = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)", date_text)
            if not m:
                continue

            day_start = int(m.group(1))
            month_str = m.group(3)
            try:
                dt_ref = datetime.strptime(f"{day_start} {month_str} {SEASON_YEAR}", "%d %B %Y")
            except ValueError:
                try:
                    dt_ref = datetime.strptime(f"{day_start} {month_str} {SEASON_YEAR}", "%d %b %Y")
                except ValueError:
                    continue

            wk_slug = slugify(raw_title)
            # Default Saturday Race 1 & Sunday Race 2
            sat_iso = dt_ref.strftime("%Y-%m-%dT12:00:00Z")
            sun_iso = dt_ref.replace(day=dt_ref.day + 1).strftime("%Y-%m-%dT12:00:00Z")

            events.append({
                "id": assign_id(f"{SPORT_KEY}-{SEASON_YEAR}-{wk_slug}-race-1"),
                "weekend": raw_title,
                "name": "Race 1",
                "utc": sat_iso,
            })
            events.append({
                "id": assign_id(f"{SPORT_KEY}-{SEASON_YEAR}-{wk_slug}-race-2"),
                "weekend": raw_title,
                "name": "Race 2",
                "utc": sun_iso,
            })

        if len(events) >= 12:
            return events
    except Exception as e:
        print(f"Live scrape fallback for FRECA ({e})", file=sys.stderr)

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
    print("Scraping FRECA 2026 schedule...", file=sys.stderr)
    events = fetch_live_freca()
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
