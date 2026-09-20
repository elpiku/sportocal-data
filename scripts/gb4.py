#!/usr/bin/env python3
"""
GB4 Championship schedule scraper for sportocal-data.
Sources official session times from MotorSport Vision (MSV) / gb-4.net & TSL Timing.
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
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "gb4" / f"{SEASON_YEAR}.json"
SPORT_KEY = "gb4"

# Official 2026 GB4 Championship Calendar
ROUNDS_2026 = [
    {
        "weekend": "Oulton Park",
        "slug": "oulton-park",
        "sessions": [
            ("quali", "Qualifying", "2026-04-04T10:00:00Z"),
            ("race-1", "Race 1", "2026-04-04T14:10:00Z"),
            ("race-2", "Race 2", "2026-04-06T09:30:00Z"),
            ("race-3", "Race 3", "2026-04-06T14:20:00Z"),
        ]
    },
    {
        "weekend": "Silverstone GP",
        "slug": "silverstone-gp",
        "sessions": [
            ("quali", "Qualifying", "2026-04-25T09:10:00Z"),
            ("race-1", "Race 1", "2026-04-25T13:20:00Z"),
            ("race-2", "Race 2", "2026-04-26T08:45:00Z"),
            ("race-3", "Race 3", "2026-04-26T13:45:00Z"),
        ]
    },
    {
        "weekend": "Donington Park GP",
        "slug": "donington-gp",
        "sessions": [
            ("quali", "Qualifying", "2026-05-23T09:20:00Z"),
            ("race-1", "Race 1", "2026-05-23T13:30:00Z"),
            ("race-2", "Race 2", "2026-05-24T09:00:00Z"),
            ("race-3", "Race 3", "2026-05-24T13:50:00Z"),
        ]
    },
    {
        "weekend": "Snetterton 300",
        "slug": "snetterton",
        "sessions": [
            ("quali", "Qualifying", "2026-07-11T09:30:00Z"),
            ("race-1", "Race 1", "2026-07-11T13:40:00Z"),
            ("race-2", "Race 2", "2026-07-12T09:10:00Z"),
            ("race-3", "Race 3", "2026-07-12T14:00:00Z"),
        ]
    },
    {
        "weekend": "Silverstone GP (Summer)",
        "slug": "silverstone-summer",
        "sessions": [
            ("quali", "Qualifying", "2026-07-25T09:10:00Z"),
            ("race-1", "Race 1", "2026-07-25T13:30:00Z"),
            ("race-2", "Race 2", "2026-07-26T08:45:00Z"),
            ("race-3", "Race 3", "2026-07-26T13:50:00Z"),
        ]
    },
    {
        "weekend": "Brands Hatch Indy",
        "slug": "brands-hatch-indy",
        "sessions": [
            ("quali", "Qualifying", "2026-09-05T09:30:00Z"),
            ("race-1", "Race 1", "2026-09-05T13:40:00Z"),
            ("race-2", "Race 2", "2026-09-06T09:10:00Z"),
            ("race-3", "Race 3", "2026-09-06T14:00:00Z"),
        ]
    },
    {
        "weekend": "Donington Park Decider",
        "slug": "donington-decider",
        "sessions": [
            ("quali", "Qualifying", "2026-10-03T09:30:00Z"),
            ("race-1", "Race 1", "2026-10-03T13:40:00Z"),
            ("race-2", "Race 2", "2026-10-04T09:10:00Z"),
            ("race-3", "Race 3", "2026-10-04T14:00:00Z"),
        ]
    },
]


def fetch_live_msv():
    """Attempt live scrape from official MSV gb-4.net calendar portal."""
    url = "https://www.gb-4.net/calendar"
    try:
        html = fetch(url, timeout=12)
        soup = BeautifulSoup(html, "html.parser")
        events = []
        assigner = make_unique_id_assigner()

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
        print(f"Live GB4 scrape fallback: {e}", file=sys.stderr)

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
