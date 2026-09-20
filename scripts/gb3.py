#!/usr/bin/env python3
"""
GB3 Championship schedule scraper for sportocal-data.
Sources official session times from MotorSport Vision (MSV) / gb-3.net & TSL Timing.
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
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "gb3" / f"{SEASON_YEAR}.json"
SPORT_KEY = "gb3"

# Official 2026 GB3 Championship Calendar
ROUNDS_2026 = [
    {
        "weekend": "Silverstone GP",
        "slug": "silverstone-gp",
        "sessions": [
            ("quali", "Qualifying", "2026-04-25T10:10:00Z"),
            ("race-1", "Race 1", "2026-04-25T14:20:00Z"),
            ("race-2", "Race 2", "2026-04-26T09:40:00Z"),
            ("race-3", "Race 3", "2026-04-26T14:45:00Z"),
        ]
    },
    {
        "weekend": "Spa-Francorchamps",
        "slug": "spa",
        "sessions": [
            ("quali", "Qualifying", "2026-05-30T08:30:00Z"),
            ("race-1", "Race 1", "2026-05-30T13:10:00Z"),
            ("race-2", "Race 2", "2026-05-31T08:50:00Z"),
            ("race-3", "Race 3", "2026-05-31T13:40:00Z"),
        ]
    },
    {
        "weekend": "Hungaroring",
        "slug": "hungaroring",
        "sessions": [
            ("quali", "Qualifying", "2026-06-20T08:30:00Z"),
            ("race-1", "Race 1", "2026-06-20T12:45:00Z"),
            ("race-2", "Race 2", "2026-06-21T08:15:00Z"),
            ("race-3", "Race 3", "2026-06-21T13:00:00Z"),
        ]
    },
    {
        "weekend": "Zandvoort",
        "slug": "zandvoort",
        "sessions": [
            ("quali", "Qualifying", "2026-07-11T08:00:00Z"),
            ("race-1", "Race 1", "2026-07-11T12:30:00Z"),
            ("race-2", "Race 2", "2026-07-12T08:15:00Z"),
            ("race-3", "Race 3", "2026-07-12T13:15:00Z"),
        ]
    },
    {
        "weekend": "Silverstone GP (Summer)",
        "slug": "silverstone-summer",
        "sessions": [
            ("quali", "Qualifying", "2026-07-25T10:10:00Z"),
            ("race-1", "Race 1", "2026-07-25T14:30:00Z"),
            ("race-2", "Race 2", "2026-07-26T09:40:00Z"),
            ("race-3", "Race 3", "2026-07-26T14:50:00Z"),
        ]
    },
    {
        "weekend": "Donington Park GP",
        "slug": "donington-gp",
        "sessions": [
            ("quali", "Qualifying", "2026-09-05T09:40:00Z"),
            ("race-1", "Race 1", "2026-09-05T13:55:00Z"),
            ("race-2", "Race 2", "2026-09-06T09:25:00Z"),
            ("race-3", "Race 3", "2026-09-06T14:15:00Z"),
        ]
    },
    {
        "weekend": "Brands Hatch GP",
        "slug": "brands-hatch-gp",
        "sessions": [
            ("quali", "Qualifying", "2026-09-26T10:20:00Z"),
            ("race-1", "Race 1", "2026-09-26T14:15:00Z"),
            ("race-2", "Race 2", "2026-09-27T10:00:00Z"),
            ("race-3", "Race 3", "2026-09-27T14:30:00Z"),
        ]
    },
]


def fetch_live_msv():
    """Attempt live scrape from official MSV gb-3.net calendar portal."""
    url = "https://www.gb-3.net/calendar"
    try:
        html = fetch(url, timeout=12)
        soup = BeautifulSoup(html, "html.parser")
        events = []
        assigner = make_unique_id_assigner()

        # Check calendar items
        cards = soup.find_all("div", class_=re.compile(r"event|round|calendar", re.I))
        for card in cards:
            h = card.find(re.compile(r"h\d"))
            if not h:
                continue
            name = h.get_text(strip=True)
            slug = slugify(name)
            time_elem = card.find("time")
            if time_elem and time_elem.get("datetime"):
                dt = time_elem["datetime"]
                base_id = f"{SPORT_KEY}-{SEASON_YEAR}-{slug}-race"
                events.append({
                    "id": assigner(base_id),
                    "weekend": name,
                    "name": "Race 1",
                    "utc": dt if dt.endswith("Z") else f"{dt}Z",
                })

        if len(events) >= 6:
            events.sort(key=lambda e: e["utc"])
            return events
    except Exception as e:
        print(f"Live GB3 scrape fallback: {e}", file=sys.stderr)

    return None


def get_calendar_events():
    events = []
    for r in ROUNDS_2026:
        weekend = r["weekend"]
        slug = r["slug"]
        assigner = make_unique_id_assigner()
        for sid, sname, utc in r["sessions"]:
            base_id = f"{SPORT_KEY}-{SEASON_YEAR}-{slug}-{sid}"
            events.append({
                "id": assigner(base_id),
                "weekend": weekend,
                "name": sname,
                "utc": utc,
            })

    events.sort(key=lambda e: e["utc"])
    return events


def main():
    print(f"Scraping {SPORT_KEY.upper()} schedule...", file=sys.stderr)
    events = fetch_live_msv()
    if not events or len(events) < 6:
        events = get_calendar_events()

    print(f"Parsed {len(events)} {SPORT_KEY.upper()} sessions", file=sys.stderr)
    output = {
        "sportKey": SPORT_KEY,
        "season": str(SEASON_YEAR),
        "events": events,
    }
    write_output(OUTPUT_PATH, output, min_events=6)


if __name__ == "__main__":
    main()
