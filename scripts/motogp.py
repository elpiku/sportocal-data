"""
MotoGP World Championship Schedule Scraper
Fetches complete weekend sessions (FP1, Practice, Q1, Q2, Sprint, Race)
via the official MotoGP PulseLive REST API and writes directly to:
- motorsport/motorcycleracing/motogp/2026.json
- motorsport/motorcycleracing/moto2/2026.json
- motorsport/motorcycleracing/moto3/2026.json
"""

import json
import re
import os
import sys
from datetime import datetime, timezone
import requests
from dateutil import parser as dt_parser

BASE_API = "https://api.motogp.pulselive.com/motogp/v1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.motogp.com",
    "Referer": "https://www.motogp.com/"
}

# Output targets matching sportocal repo tree
OUTPUT_FILES = {
    "motogp": os.path.join(os.path.dirname(__file__), "../motorsport/motorcycleracing/motogp/2026.json"),
    "moto2": os.path.join(os.path.dirname(__file__), "../motorsport/motorcycleracing/moto2/2026.json"),
    "moto3": os.path.join(os.path.dirname(__file__), "../motorsport/motorcycleracing/moto3/2026.json"),
}

def slugify(text: str) -> str:
    """Standardizes names into URL-friendly IDs."""
    if not text:
        return "event"
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_-]+", "-", text)

def parse_iso_utc(date_str: str) -> str:
    """Standardizes date strings to UTC ISO-8601 strings."""
    if not date_str:
        return None
    try:
        dt = dt_parser.parse(str(date_str))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None

def normalize_session_key(session_type: str, shortname: str) -> tuple[str, str]:
    """Standardizes session naming to match the motorsport schema."""
    label = f"{session_type} {shortname}".lower().strip()
    if "free practice 1" in label or "fp1" in label:
        return "fp1", "Free Practice 1"
    elif "free practice 2" in label or "fp2" in label:
        return "fp2", "Free Practice 2"
    elif "practice" in label and "free" not in label and "pr" in label:
        return "practice", "Practice"
    elif "qualifying 1" in label or "q1" in label:
        return "qualifying_1", "Qualifying 1"
    elif "qualifying 2" in label or "q2" in label:
        return "qualifying_2", "Qualifying 2"
    elif "qualifying" in label:
        return "qualifying", "Qualifying"
    elif "sprint" in label or "spr" in label:
        return "sprint", "Sprint"
    elif "race" in label or "rac" in label or "grand prix" in label:
        return "race", "Grand Prix Race"
    elif "warm up" in label or "wup" in label:
        return "warmup", "Warm Up"
    return slugify(label).replace("-", "_"), shortname or session_type

def get_season_uuid(season_year: int) -> str:
    """Retrieves the season UUID from MotoGP metadata."""
    url = f"{BASE_API}/results/seasons"
    print(f"Fetching seasons catalog: {url}")
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    seasons = res.json()

    for s in seasons:
        if s.get("year") == season_year:
            return s.get("id")

    # Fallback to current season
    for s in seasons:
        if s.get("current"):
            return s.get("id")
    return seasons[0].get("id") if seasons else None

def scrape_motogp(season_year: int = 2026):
    season_uuid = get_season_uuid(season_year)
    if not season_uuid:
        print(f"Season UUID not found for year {season_year}")
        return

    events_url = f"{BASE_API}/results/events?seasonUuid={season_uuid}"
    print(f"Fetching Grand Prix events: {events_url}")
    res = requests.get(events_url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    events_raw = res.json()

    category_schedules = {
        "motogp": [],
        "moto2": [],
        "moto3": []
    }

    round_idx = 1
    for ev in events_raw:
        # Exclude pre-season test events
        if ev.get("test"):
            continue

        event_uuid = ev.get("id")
        event_name = ev.get("name", f"Grand Prix {round_idx}")
        circuit_info = ev.get("circuit", {}) or {}
        circuit_name = circuit_info.get("name", "Unknown Circuit")
        country_name = ev.get("country", {}).get("name", "")
        city_name = circuit_info.get("city", "")

        event_id = f"{season_year}-{slugify(event_name)}"

        # Fetch detailed weekend timetable
        sched_url = f"{BASE_API}/results/events/{event_uuid}/schedule"
        cat_sessions = {"motogp": {}, "moto2": {}, "moto3": {}}

        try:
            sched_res = requests.get(sched_url, headers=HEADERS, timeout=12)
            if sched_res.status_code == 200:
                sched_data = sched_res.json()
                for s in sched_data:
                    cat_name = (s.get("category", {}).get("name") or "").lower().strip()
                    if cat_name in cat_sessions:
                        s_type = s.get("type", "")
                        s_short = s.get("shortname", "")
                        s_start = s.get("date")

                        if s_start:
                            s_key, display_name = normalize_session_key(s_type, s_short)
                            cat_sessions[cat_name][s_key] = {
                                "name": display_name,
                                "start": parse_iso_utc(s_start),
                                "status": "scheduled"
                            }
        except Exception as e:
            print(f"Error fetching session timetable for {event_name}: {e}")

        # Date fallback if weekend endpoint was not yet populated
        fallback_date = ev.get("date_start") or ev.get("date_end")

        for cat in ["motogp", "moto2", "moto3"]:
            sessions = cat_sessions[cat]
            if "race" not in sessions and fallback_date:
                sessions["race"] = {
                    "name": f"{event_name} Race",
                    "start": parse_iso_utc(fallback_date),
                    "status": "scheduled"
                }

            category_schedules[cat].append({
                "id": event_id,
                "round": round_idx,
                "name": event_name,
                "circuit": {
                    "name": circuit_name,
                    "city": city_name,
                    "country": country_name
                },
                "sessions": sessions
            })

        round_idx += 1

    # Write out data to motorsport/motorcycleracing/{category}/2026.json
    for cat, file_path in OUTPUT_FILES.items():
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        payload = {
            "sport": cat,
            "season": season_year,
            "events": category_schedules[cat]
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(category_schedules[cat])} events to {file_path}")

def main():
    scrape_motogp(2026)

if __name__ == "__main__":
    main()
