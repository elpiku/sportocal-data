#!/usr/bin/env python3
"""
GT World Challenge Europe schedule scraper for sportocal-data.
Sources official session times from SRO Motorsports Group (gt-world-challenge-europe.com).
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
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "gt-world-challenge-europe" / f"{SEASON_YEAR}.json"
SPORT_KEY = "gt-world-challenge-europe"

# Official 2026 Fanatec GT World Challenge Europe Powered by AWS Calendar
ROUNDS_2026 = [
    {
        "weekend": "Paul Ricard 500km",
        "slug": "paul-ricard",
        "sessions": [
            ("fp", "Free Practice", "2026-04-10T07:00:00Z"),
            ("pre-quali", "Pre-Qualifying", "2026-04-10T12:05:00Z"),
            ("quali", "Qualifying", "2026-04-11T07:45:00Z"),
            ("race", "Paul Ricard 500km Race", "2026-04-11T13:00:00Z"),
        ]
    },
    {
        "weekend": "Brands Hatch (Sprint)",
        "slug": "brands-hatch",
        "sessions": [
            ("fp", "Free Practice", "2026-05-02T08:00:00Z"),
            ("pre-quali", "Pre-Qualifying", "2026-05-02T11:15:00Z"),
            ("quali-1", "Qualifying 1", "2026-05-02T15:05:00Z"),
            ("quali-2", "Qualifying 2", "2026-05-03T08:10:00Z"),
            ("race-1", "Race 1", "2026-05-03T10:00:00Z"),
            ("race-2", "Race 2", "2026-05-03T15:00:00Z"),
        ]
    },
    {
        "weekend": "Misano (Sprint)",
        "slug": "misano",
        "sessions": [
            ("fp", "Free Practice", "2026-05-15T07:00:00Z"),
            ("pre-quali", "Pre-Qualifying", "2026-05-15T13:10:00Z"),
            ("quali-1", "Qualifying 1", "2026-05-16T08:00:00Z"),
            ("race-1", "Race 1", "2026-05-16T12:00:00Z"),
            ("quali-2", "Qualifying 2", "2026-05-17T07:30:00Z"),
            ("race-2", "Race 2", "2026-05-17T12:00:00Z"),
        ]
    },
    {
        "weekend": "Monza 3 Hours",
        "slug": "monza",
        "sessions": [
            ("fp", "Free Practice", "2026-05-29T07:00:00Z"),
            ("pre-quali", "Pre-Qualifying", "2026-05-29T13:30:00Z"),
            ("quali", "Qualifying", "2026-05-30T07:45:00Z"),
            ("race", "Monza 3 Hours Race", "2026-05-31T13:00:00Z"),
        ]
    },
    {
        "weekend": "CrowdStrike 24 Hours of Spa",
        "slug": "spa-24h",
        "sessions": [
            ("fp", "Free Practice", "2026-06-25T09:20:00Z"),
            ("pre-quali", "Pre-Qualifying", "2026-06-25T16:10:00Z"),
            ("quali", "Qualifying", "2026-06-25T19:20:00Z"),
            ("superpole", "Superpole", "2026-06-26T13:40:00Z"),
            ("race", "24 Hours of Spa Race", "2026-06-27T14:30:00Z"),
        ]
    },
    {
        "weekend": "Misano Sprint",
        "slug": "hockenheim",
        "sessions": [
            ("fp", "Free Practice", "2026-07-17T07:00:00Z"),
            ("pre-quali", "Pre-Qualifying", "2026-07-17T12:20:00Z"),
            ("quali-1", "Qualifying 1", "2026-07-18T07:50:00Z"),
            ("race-1", "Race 1", "2026-07-18T12:15:00Z"),
            ("quali-2", "Qualifying 2", "2026-07-19T07:45:00Z"),
            ("race-2", "Race 2", "2026-07-19T12:15:00Z"),
        ]
    },
    {
        "weekend": "Nürburgring 3 Hours",
        "slug": "nurburgring",
        "sessions": [
            ("fp", "Free Practice", "2026-08-28T06:30:00Z"),
            ("pre-quali", "Pre-Qualifying", "2026-08-28T11:25:00Z"),
            ("quali", "Qualifying", "2026-08-29T06:45:00Z"),
            ("race", "Nürburgring 3 Hours Race", "2026-08-30T13:00:00Z"),
        ]
    },
    {
        "weekend": "Magny-Cours (Sprint)",
        "slug": "magny-cours",
        "sessions": [
            ("fp", "Free Practice", "2026-09-11T07:30:00Z"),
            ("pre-quali", "Pre-Qualifying", "2026-09-11T12:50:00Z"),
            ("quali-1", "Qualifying 1", "2026-09-12T07:05:00Z"),
            ("race-1", "Race 1", "2026-09-12T12:45:00Z"),
            ("quali-2", "Qualifying 2", "2026-09-13T07:00:00Z"),
            ("race-2", "Race 2", "2026-09-13T12:45:00Z"),
        ]
    },
    {
        "weekend": "Valencia (Sprint)",
        "slug": "valencia",
        "sessions": [
            ("fp", "Free Practice", "2026-09-18T07:00:00Z"),
            ("pre-quali", "Pre-Qualifying", "2026-09-18T12:20:00Z"),
            ("quali-1", "Qualifying 1", "2026-09-19T07:00:00Z"),
            ("race-1", "Race 1", "2026-09-19T12:00:00Z"),
            ("quali-2", "Qualifying 2", "2026-09-20T07:00:00Z"),
            ("race-2", "Race 2", "2026-09-20T12:00:00Z"),
        ]
    },
    {
        "weekend": "Barcelona 3 Hours",
        "slug": "barcelona",
        "sessions": [
            ("fp", "Free Practice", "2026-10-09T07:00:00Z"),
            ("pre-quali", "Pre-Qualifying", "2026-10-09T11:40:00Z"),
            ("quali", "Qualifying", "2026-10-10T07:45:00Z"),
            ("race", "Barcelona 3 Hours Race", "2026-10-11T13:00:00Z"),
        ]
    },
]


def fetch_live_sro():
    """Attempt live scrape from official SRO GT World Challenge Europe portal."""
    url = "https://www.gt-world-challenge-europe.com/calendar"
    try:
        html = fetch(url, timeout=15)
        soup = BeautifulSoup(html, "html.parser")
        events = []
        assigner = make_unique_id_assigner()

        # Check for event blocks
        event_cards = soup.find_all("div", class_=re.compile(r"event|calendar-item", re.I))
        for card in event_cards:
            title = card.find(re.compile(r"h\d"))
            if not title:
                continue
            name = title.get_text(strip=True)
            slug = slugify(name)
            time_elem = card.find("time") or card.find(class_=re.compile(r"date|time", re.I))
            if time_elem and time_elem.get("datetime"):
                dt_str = time_elem["datetime"]
                base_id = f"{SPORT_KEY}-{SEASON_YEAR}-{slug}-race"
                events.append({
                    "id": assigner(base_id),
                    "weekend": name,
                    "name": "Race",
                    "utc": dt_str if dt_str.endswith("Z") else f"{dt_str}Z",
                })

        if len(events) >= 10:
            events.sort(key=lambda e: e["utc"])
            return events
    except Exception as e:
        print(f"Live SRO GT scrape fallback: {e}", file=sys.stderr)

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
    events = fetch_live_sro()
    if not events or len(events) < 10:
        events = get_calendar_events()

    print(f"Parsed {len(events)} {SPORT_KEY.upper()} sessions", file=sys.stderr)
    output = {
        "sportKey": SPORT_KEY,
        "season": str(SEASON_YEAR),
        "events": events,
    }
    write_output(OUTPUT_PATH, output, min_events=10)


if __name__ == "__main__":
    main()
