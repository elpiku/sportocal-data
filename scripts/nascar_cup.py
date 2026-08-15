"""
NASCAR Cup Series Schedule Scraper
Fetches complete weekend schedules (Practice, Qualifying, Race)
and formats them to match the Sportocal data schema.
"""

import json
import re
import os
import sys
from datetime import datetime, timezone
import requests
from dateutil import parser as dt_parser
import pytz

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "../motorsport/nascar/cup/2026.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9"
}

def slugify(text: str) -> str:
    """Standardizes names into URL-friendly IDs."""
    if not text:
        return "event"
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_-]+", "-", text)

def parse_iso_utc(date_str: str, default_tz: str = "America/New_York") -> str:
    """Converts date string to UTC ISO-8601 string."""
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
    """Standardizes session names across practice, qualifying, and race."""
    name_lower = raw_name.lower().strip()
    if "practice 1" in name_lower or "first practice" in name_lower:
        return "practice_1", "Practice 1"
    elif "practice 2" in name_lower or "final practice" in name_lower:
        return "practice_2", "Practice 2"
    elif "practice" in name_lower:
        return "practice", "Practice"
    elif "qualifying" in name_lower or "pole" in name_lower or "time trials" in name_lower:
        return "qualifying", "Qualifying"
    elif "duel" in name_lower or "heat" in name_lower:
        return "duels", raw_name
    elif "race" in name_lower or "400" in name_lower or "500" in name_lower:
        return "race", "Race"
    else:
        key = slugify(raw_name).replace("-", "_")
        return key, raw_name

def fetch_espn_season_schedule(season_year: int = 2026) -> list:
    """
    Fetches the entire season calendar across all racing events from ESPN.
    """
    url = f"https://site.api.espn.com/apis/site/v2/sports/racing/nascar-premier/scoreboard?limit=1000&dates={season_year}"
    print(f"Requesting ESPN NASCAR Cup schedule: {url}")
    
    events_list = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            # Try alternate sport slug if nascar-premier didn't return 200
            alt_url = f"https://site.api.espn.com/apis/site/v2/sports/racing/nascar-cup/scoreboard?limit=1000&dates={season_year}"
            res = requests.get(alt_url, headers=HEADERS, timeout=15)
            
        data = res.json()
        raw_events = data.get("events", [])
        print(f"Found {len(raw_events)} raw events from ESPN")

        round_num = 1
        for ev in raw_events:
            name = ev.get("name") or ev.get("shortName", f"NASCAR Cup Race {round_num}")
            
            competitions = ev.get("competitions", [])
            venue = competitions[0].get("venue", {}) if competitions else {}
            circuit_name = venue.get("fullName") or ev.get("circuit", {}).get("name", "Unknown Track")
            city = venue.get("address", {}).get("city", "")
            state = venue.get("address", {}).get("state", "")
            country = venue.get("address", {}).get("country", "USA")

            sessions = {}

            # Parse sub-sessions (Practices, Qualifying, Main Race)
            for comp in competitions:
                comp_type = comp.get("type", {}).get("text", "")
                comp_date = comp.get("date")
                status = comp.get("status", {}).get("type", {}).get("name", "STATUS_SCHEDULED").lower()
                status_clean = "completed" if "final" in status else "scheduled"

                if not comp_date:
                    continue

                session_key, display_name = normalize_session_key(comp_type or name)
                sessions[session_key] = {
                    "name": display_name,
                    "start": parse_iso_utc(comp_date),
                    "end": None,
                    "status": status_clean
                }

            # Top-level fallback for main race
            if "race" not in sessions and ev.get("date"):
                race_status = "completed" if "final" in ev.get("status", {}).get("type", {}).get("name", "").lower() else "scheduled"
                sessions["race"] = {
                    "name": name,
                    "start": parse_iso_utc(ev.get("date")),
                    "end": None,
                    "status": race_status
                }

            events_list.append({
                "id": f"{season_year}-{slugify(name)}",
                "round": round_num,
                "name": name,
                "circuit": {
                    "name": circuit_name,
                    "city": city,
                    "state": state,
                    "country": country
                },
                "sessions": sessions
            })
            round_num += 1

    except Exception as e:
        print(f"Failed to parse ESPN feed: {e}")

    return events_list

def main():
    season_year = 2026
    events = fetch_espn_season_schedule(season_year)

    payload = {
        "sport": "nascar-cup",
        "season": season_year,
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "events": events
    }

    target_path = os.path.abspath(OUTPUT_PATH)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(events)} events to {target_path}")

if __name__ == "__main__":
    main()
