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
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nascar.com",
    "Referer": "https://www.nascar.com/schedule/"
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
    """Categorizes session type into standard keys."""
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

def fetch_from_nascar_api(season_year: int) -> list:
    """Tries official NASCAR CDN endpoints."""
    urls = [
        f"https://cf.nascar.com/c/nascar-api/season/{season_year}/series/1/schedule.json",
        f"https://cf.nascar.com/c/nascar-api/season/schedule.json"
    ]
    for url in urls:
        try:
            print(f"Trying NASCAR endpoint: {url}")
            res = requests.get(url, headers=HEADERS, timeout=12)
            if res.status_code == 200 and res.content:
                data = res.json()
                races = data.get("response", data) if isinstance(data, dict) else data
                if isinstance(races, list) and len(races) > 0:
                    events = []
                    round_num = 1
                    for item in races:
                        if item.get("series_id") and item.get("series_id") != 1:
                            continue
                        name = item.get("race_name") or item.get("event_name", f"NASCAR Cup Race {round_num}")
                        circuit = item.get("track_name", "Unknown Track")
                        sessions = {}

                        for s in item.get("weekend_schedule") or item.get("schedule") or []:
                            s_name = s.get("session_name") or s.get("description", "")
                            s_start = s.get("start_time_utc") or s.get("start_time")
                            s_end = s.get("end_time_utc") or s.get("end_time")
                            if s_start:
                                k, display = normalize_session_key(s_name)
                                sessions[k] = {
                                    "name": display,
                                    "start": parse_iso_utc(s_start),
                                    "end": parse_iso_utc(s_end) if s_end else None,
                                    "status": s.get("status", "scheduled").lower()
                                }

                        if "race" not in sessions and (item.get("race_date") or item.get("start_time")):
                            sessions["race"] = {
                                "name": name,
                                "start": parse_iso_utc(item.get("race_date") or item.get("start_time")),
                                "end": None,
                                "status": item.get("race_status", "scheduled").lower()
                            }

                        events.append({
                            "id": f"{season_year}-{slugify(name)}",
                            "round": round_num,
                            "name": name,
                            "circuit": {
                                "name": circuit,
                                "city": item.get("city", ""),
                                "state": item.get("state", ""),
                                "country": item.get("country", "USA")
                            },
                            "sessions": sessions
                        })
                        round_num += 1
                    if events:
                        return events
        except Exception as e:
            print(f"Error on {url}: {e}")
    return []

def fetch_from_espn_api(season_year: int) -> list:
    """Fetches complete full-season schedule from ESPN."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/racing/nascar-premier/scoreboard?limit=100&dates={season_year}"
    print(f"Fetching from ESPN API: {url}")
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        if res.status_code != 200:
            return []
        data = res.json()
        raw_events = data.get("events", [])
        events = []
        round_num = 1
        for ev in raw_events:
            name = ev.get("name") or ev.get("shortName", f"NASCAR Cup Race {round_num}")
            venue = ev.get("competitions", [{}])[0].get("venue", {}) if ev.get("competitions") else {}
            circuit_name = venue.get("fullName", "Unknown Track")
            city = venue.get("address", {}).get("city", "")
            state = venue.get("address", {}).get("state", "")

            sessions = {}
            for comp in ev.get("competitions", []):
                c_type = comp.get("type", {}).get("text", "")
                c_date = comp.get("date")
                status = "completed" if "final" in comp.get("status", {}).get("type", {}).get("name", "").lower() else "scheduled"
                if c_date:
                    k, display = normalize_session_key(c_type or name)
                    sessions[k] = {
                        "name": display,
                        "start": parse_iso_utc(c_date),
                        "end": None,
                        "status": status
                    }

            if "race" not in sessions and ev.get("date"):
                sessions["race"] = {
                    "name": name,
                    "start": parse_iso_utc(ev.get("date")),
                    "end": None,
                    "status": "completed" if "final" in ev.get("status", {}).get("type", {}).get("name", "").lower() else "scheduled"
                }

            events.append({
                "id": f"{season_year}-{slugify(name)}",
                "round": round_num,
                "name": name,
                "circuit": {
                    "name": circuit_name,
                    "city": city,
                    "state": state,
                    "country": "USA"
                },
                "sessions": sessions
            })
            round_num += 1
        return events
    except Exception as e:
        print(f"Error on ESPN fetch: {e}")
        return []

def main():
    season_year = 2026
    events = fetch_from_nascar_api(season_year)
    if not events:
        print("NASCAR direct API returned no events. Falling back to ESPN...")
        events = fetch_from_espn_api(season_year)

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

    print(f"Successfully written {len(events)} events to {target_path}")

if __name__ == "__main__":
    main()
