"""
NASCAR Cup Series Schedule Scraper
Fetches complete weekend schedules (Practice, Qualifying, Race)
via the ESPN Core Racing API (sports.core.api.espn.com).
"""

import json
import re
import os
from datetime import datetime, timezone
import requests
from dateutil import parser as dt_parser
import pytz

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "../motorsport/nascar/cup/2026.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*"
}

def slugify(text: str) -> str:
    """Standardizes names into URL-friendly IDs."""
    if not text:
        return "event"
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_-]+", "-", text)

def parse_iso_utc(date_str: str) -> str:
    """Converts date string to UTC ISO-8601 string."""
    if not date_str:
        return None
    try:
        dt = dt_parser.parse(str(date_str))
        if dt.tzinfo is None:
            local_tz = pytz.timezone("America/New_York")
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

def fetch_espn_core_schedule(season_year: int = 2026) -> list:
    """
    Fetches the full season calendar directly from ESPN Core REST endpoints.
    """
    base_url = f"https://sports.core.api.espn.com/v2/sports/racing/leagues/nascar-premier/seasons/{season_year}/types/2/events?limit=100"
    print(f"Fetching event catalog from: {base_url}")
    
    try:
        res = requests.get(base_url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"Error fetching event catalog: {e}")
        return []

    items = data.get("items", [])
    print(f"Found {len(items)} event references to parse.")

    events_list = []
    round_num = 1

    for item in items:
        event_url = item.get("$ref") if isinstance(item, dict) else item
        if not event_url:
            continue

        try:
            ev_res = requests.get(event_url, headers=HEADERS, timeout=10)
            if ev_res.status_code != 200:
                continue
            ev = ev_res.json()

            name = ev.get("name") or ev.get("shortName", f"NASCAR Cup Race {round_num}")
            venue_info = ev.get("venues", [{}])[0] if ev.get("venues") else {}
            circuit_name = venue_info.get("fullName", "Unknown Track")
            city = venue_info.get("address", {}).get("city", "")
            state = venue_info.get("address", {}).get("state", "")
            country = venue_info.get("address", {}).get("country", "USA")

            sessions = {}

            # Parse competitions / sub-sessions
            comps = ev.get("competitions", [])
            for comp in comps:
                comp_url = comp.get("$ref") if isinstance(comp, dict) else None
                comp_data = comp
                if comp_url:
                    try:
                        c_res = requests.get(comp_url, headers=HEADERS, timeout=10)
                        if c_res.status_code == 200:
                            comp_data = c_res.json()
                    except Exception:
                        pass

                comp_type = comp_data.get("type", {}).get("text", "")
                comp_date = comp_data.get("date")
                status = comp_data.get("status", {}).get("type", {}).get("name", "STATUS_SCHEDULED").lower()
                status_clean = "completed" if "final" in status else "scheduled"

                if comp_date:
                    k, display = normalize_session_key(comp_type or name)
                    sessions[k] = {
                        "name": display,
                        "start": parse_iso_utc(comp_date),
                        "end": None,
                        "status": status_clean
                    }

            # Top-level event date fallback for race
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
            print(f"Error parsing event {event_url}: {e}")

    return events_list

def main():
    season_year = 2026
    events = fetch_espn_core_schedule(season_year)

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

    print(f"Successfully saved {len(events)} events to {target_path}")

if __name__ == "__main__":
    main()
