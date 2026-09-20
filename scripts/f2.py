#!/usr/bin/env python3
"""
Formula 2 Championship schedule scraper for sportocal-data.
Sources official session times from FOM / FIA Formula 2 (fiaformula2.com & api.formula1.com).
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
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "f2" / f"{SEASON_YEAR}.json"
SPORT_KEY = "f2"

# 2026 FIA Formula 2 Championship Calendar & Timetables
# F2 travels with F1 across 14 rounds.
ROUNDS_2026 = [
    {
        "weekend": "Melbourne Grand Prix",
        "slug": "melbourne",
        "sessions": [
            ("practice", "Free Practice", "2026-03-06T01:00:00Z"),
            ("quali", "Qualifying", "2026-03-06T06:30:00Z"),
            ("sprint", "Sprint Race", "2026-03-07T03:15:00Z"),
            ("feature", "Feature Race", "2026-03-08T00:30:00Z"),
        ]
    },
    {
        "weekend": "Sakhir Grand Prix",
        "slug": "sakhir",
        "sessions": [
            ("practice", "Free Practice", "2026-04-10T08:05:00Z"),
            ("quali", "Qualifying", "2026-04-10T13:55:00Z"),
            ("sprint", "Sprint Race", "2026-04-11T14:15:00Z"),
            ("feature", "Feature Race", "2026-04-12T10:25:00Z"),
        ]
    },
    {
        "weekend": "Jeddah Grand Prix",
        "slug": "jeddah",
        "sessions": [
            ("practice", "Free Practice", "2026-04-17T11:00:00Z"),
            ("quali", "Qualifying", "2026-04-17T15:00:00Z"),
            ("sprint", "Sprint Race", "2026-04-18T15:15:00Z"),
            ("feature", "Feature Race", "2026-04-19T13:25:00Z"),
        ]
    },
    {
        "weekend": "Emilia Romagna Grand Prix",
        "slug": "imola",
        "sessions": [
            ("practice", "Free Practice", "2026-05-15T09:05:00Z"),
            ("quali", "Qualifying", "2026-05-15T14:00:00Z"),
            ("sprint", "Sprint Race", "2026-05-16T12:15:00Z"),
            ("feature", "Feature Race", "2026-05-17T08:00:00Z"),
        ]
    },
    {
        "weekend": "Monaco Grand Prix",
        "slug": "monaco",
        "sessions": [
            ("practice", "Free Practice", "2026-05-21T13:00:00Z"),
            ("quali", "Qualifying", "2026-05-22T13:10:00Z"),
            ("sprint", "Sprint Race", "2026-05-23T12:15:00Z"),
            ("feature", "Feature Race", "2026-05-24T07:40:00Z"),
        ]
    },
    {
        "weekend": "Spanish Grand Prix",
        "slug": "barcelona",
        "sessions": [
            ("practice", "Free Practice", "2026-05-29T09:05:00Z"),
            ("quali", "Qualifying", "2026-05-29T13:55:00Z"),
            ("sprint", "Sprint Race", "2026-05-30T12:15:00Z"),
            ("feature", "Feature Race", "2026-05-31T09:35:00Z"),
        ]
    },
    {
        "weekend": "Austrian Grand Prix",
        "slug": "spielberg",
        "sessions": [
            ("practice", "Free Practice", "2026-06-26T08:05:00Z"),
            ("quali", "Qualifying", "2026-06-26T12:55:00Z"),
            ("sprint", "Sprint Race", "2026-06-27T11:45:00Z"),
            ("feature", "Feature Race", "2026-06-28T08:35:00Z"),
        ]
    },
    {
        "weekend": "British Grand Prix",
        "slug": "silverstone",
        "sessions": [
            ("practice", "Free Practice", "2026-07-03T09:00:00Z"),
            ("quali", "Qualifying", "2026-07-03T14:05:00Z"),
            ("sprint", "Sprint Race", "2026-07-04T12:15:00Z"),
            ("feature", "Feature Race", "2026-07-05T08:55:00Z"),
        ]
    },
    {
        "weekend": "Belgian Grand Prix",
        "slug": "spa",
        "sessions": [
            ("practice", "Free Practice", "2026-07-24T09:05:00Z"),
            ("quali", "Qualifying", "2026-07-24T13:55:00Z"),
            ("sprint", "Sprint Race", "2026-07-25T12:15:00Z"),
            ("feature", "Feature Race", "2026-07-26T08:00:00Z"),
        ]
    },
    {
        "weekend": "Hungarian Grand Prix",
        "slug": "budapest",
        "sessions": [
            ("practice", "Free Practice", "2026-07-31T09:05:00Z"),
            ("quali", "Qualifying", "2026-07-31T14:00:00Z"),
            ("sprint", "Sprint Race", "2026-08-01T12:15:00Z"),
            ("feature", "Feature Race", "2026-08-02T08:05:00Z"),
        ]
    },
    {
        "weekend": "Italian Grand Prix",
        "slug": "monza",
        "sessions": [
            ("practice", "Free Practice", "2026-09-04T09:05:00Z"),
            ("quali", "Qualifying", "2026-09-04T14:00:00Z"),
            ("sprint", "Sprint Race", "2026-09-05T12:15:00Z"),
            ("feature", "Feature Race", "2026-09-06T08:05:00Z"),
        ]
    },
    {
        "weekend": "Azerbaijan Grand Prix",
        "slug": "baku",
        "sessions": [
            ("practice", "Free Practice", "2026-09-25T07:00:00Z"),
            ("quali", "Qualifying", "2026-09-25T11:00:00Z"),
            ("sprint", "Sprint Race", "2026-09-26T10:15:00Z"),
            ("feature", "Feature Race", "2026-09-27T07:35:00Z"),
        ]
    },
    {
        "weekend": "Qatar Grand Prix",
        "slug": "lusail",
        "sessions": [
            ("practice", "Free Practice", "2026-11-27T11:05:00Z"),
            ("quali", "Qualifying", "2026-11-27T16:10:00Z"),
            ("sprint", "Sprint Race", "2026-11-28T16:20:00Z"),
            ("feature", "Feature Race", "2026-11-29T12:20:00Z"),
        ]
    },
    {
        "weekend": "Abu Dhabi Grand Prix",
        "slug": "abudhabi",
        "sessions": [
            ("practice", "Free Practice", "2026-12-04T07:05:00Z"),
            ("quali", "Qualifying", "2026-12-04T11:00:00Z"),
            ("sprint", "Sprint Race", "2026-12-05T12:15:00Z"),
            ("feature", "Feature Race", "2026-12-06T09:15:00Z"),
        ]
    },
]


def fetch_live_f2():
    """Attempt live scrape from official FIA Formula 2 Next.js race hubs."""
    url = "https://www.fiaformula2.com/en/racing"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None
        html = resp.text
        # Look for SSR data chunks with JSON sessions
        json_matches = re.findall(r'(\{"roundNumber":\d+.*?"sessions":\[.*?\]\})', html)
        if not json_matches:
            return None

        events = []
        assigner = make_unique_id_assigner()
        for j_str in json_matches:
            try:
                round_data = json.loads(j_str)
                weekend = round_data.get("countryName") or round_data.get("circuitName") or "Grand Prix"
                if not weekend.endswith("Grand Prix"):
                    weekend = f"{weekend} Grand Prix"
                slug = slugify(round_data.get("circuitId", "gp"))

                for s in round_data.get("sessions", []):
                    s_name = s.get("sessionName", "Session")
                    start_utc = s.get("startTimeUtc") or s.get("startTime")
                    if not start_utc:
                        continue
                    sid = slugify(s_name)
                    base_id = f"{SPORT_KEY}-{SEASON_YEAR}-{slug}-{sid}"
                    events.append({
                        "id": assigner(base_id),
                        "weekend": weekend,
                        "name": s_name,
                        "utc": start_utc if start_utc.endswith("Z") else f"{start_utc}Z",
                    })
            except Exception:
                continue

        if len(events) >= 10:
            events.sort(key=lambda e: e["utc"])
            return events
    except Exception as e:
        print(f"Live F2 scrape fallback: {e}", file=sys.stderr)

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
    events = fetch_live_f2()
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
