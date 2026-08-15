"""
NASCAR Cup Series Schedule Scraper
Fetches complete weekend schedules (Practice, Qualifying, Race) from the NASCAR official API
and transforms them into the canonical Sportocal motorsport JSON schema.
"""

import json
import re
import os
import sys
from datetime import datetime, timezone
import requests
from dateutil import parser as dt_parser
import pytz

NASCAR_SCHEDULE_URL = "https://cf.nascar.com/c/nascar-api/season/schedule.json"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "../motorsport/nascar/cup/2026.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nascar.com/schedule/"
}

def slugify(text: str) -> str:
    """Standardizes race names into URL-friendly IDs."""
    if not text:
        return "event"
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_-]+", "-", text)

def parse_iso_utc(date_str: str, default_tz: str = "America/New_York") -> str:
    """Parses date string and formats to ISO-8601 UTC string (YYYY-MM-DDTHH:MM:SSZ)."""
    if not date_str:
        return None
    try:
        dt = dt_parser.parse(str(date_str))
        if dt.tzinfo is None:
            local_tz = pytz.timezone(default_tz)
            dt = local_tz.localize(dt)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None

def normalize_session_key(raw_name: str) -> tuple[str, str]:
    """
    Standardizes session labels:
    practice_1, practice_2, qualifying, duels, race.
    """
    name_lower = raw_name.lower().strip()
    if "practice 1" in name_lower or "first practice" in name_lower:
        return "practice_1", "Practice 1"
    elif "practice 2" in name_lower or "final practice" in name_lower:
        return "practice_2", "Practice 2"
    elif "practice" in name_lower:
        return "practice", "Practice"
    elif "qualifying" in name_lower or "pole qualifying" in name_lower or "time trials" in name_lower:
        return "qualifying", "Qualifying"
    elif "duel" in name_lower or "heat" in name_lower:
        return "duels", raw_name
    elif "race" in name_lower or "400" in name_lower or "500" in name_lower:
        return "race", "Race"
    else:
        key = slugify(raw_name).replace("-", "_")
        return key, raw_name

def fetch_nascar_cup_schedule(season_year: int = None) -> dict:
    if season_year is None:
        season_year = datetime.now().year

    print(f"Fetching NASCAR schedule for season {season_year}...")
    try:
        response = requests.get(NASCAR_SCHEDULE_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        raw_data = response.json()
    except Exception as e:
        print(f"Error fetching NASCAR schedule: {e}")
        return {
            "sport": "nascar-cup",
            "season": season_year,
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "events": []
        }

    races = raw_data.get("response", raw_data) if isinstance(raw_data, dict) else raw_data
    if not isinstance(races, list):
        races = []

    events_list = []
    round_num = 1

    for item in races:
        # series_id == 1 indicates NASCAR Cup Series
        series_id = item.get("series_id", 1)
        if series_id != 1:
            continue

        race_name = item.get("race_name") or item.get("event_name", f"NASCAR Cup Race {round_num}")
        track_name = item.get("track_name", "Unknown Circuit")
        city = item.get("city", "")
        state = item.get("state", "")
        country = item.get("country", "USA")

        event_id = f"{season_year}-{slugify(race_name)}"
        sessions = {}

        # Parse weekend schedule breakdown (Practices, Qualifying, Duels)
        weekend_sessions = item.get("weekend_schedule") or item.get("schedule") or []
        for s in weekend_sessions:
            s_name = s.get("session_name") or s.get("description", "")
            s_start = s.get("start_time_utc") or s.get("start_time")
            s_end = s.get("end_time_utc") or s.get("end_time")

            if not s_start:
                continue

            session_key, display_name = normalize_session_key(s_name)
            sessions[session_key] = {
                "name": display_name,
                "start": parse_iso_utc(s_start),
                "end": parse_iso_utc(s_end) if s_end else None,
                "status": s.get("status", "scheduled").lower()
            }

        # Top-level fallbacks if weekend_schedule array is missing
        if "practice" not in sessions and "practice_1" not in sessions and item.get("practice_start_time"):
            sessions["practice"] = {
                "name": "Practice",
                "start": parse_iso_utc(item.get("practice_start_time")),
                "end": None,
                "status": "scheduled"
            }

        if "qualifying" not in sessions and item.get("qualifying_start_time"):
            sessions["qualifying"] = {
                "name": "Qualifying",
                "start": parse_iso_utc(item.get("qualifying_start_time")),
                "end": None,
                "status": "scheduled"
            }

        # Race session
        race_start = item.get("race_date") or item.get("start_time")
        if "race" not in sessions and race_start:
            sessions["race"] = {
                "name": race_name,
                "start": parse_iso_utc(race_start),
                "end": None,
                "status": item.get("race_status", "scheduled").lower()
            }

        events_list.append({
            "id": event_id,
            "round": round_num,
            "name": race_name,
            "circuit": {
                "name": track_name,
                "city": city,
                "state": state,
                "country": country
            },
            "sessions": sessions
        })
        round_num += 1

    return {
        "sport": "nascar-cup",
        "season": season_year,
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "events": events_list
    }

def main():
    data = fetch_nascar_cup_schedule()
    target_path = os.path.abspath(OUTPUT_PATH)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(data['events'])} events to {target_path}")

if __name__ == "__main__":
    main()
