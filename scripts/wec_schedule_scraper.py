#!/usr/bin/env python3
"""
WEC (FIA World Endurance Championship) schedule scraper for the
sportocal-data repo. Writes motorsport/wec/2026.json.

Two-step scrape against the official site (fiawec.com):

  1. Any page on the site carries the full season's calendar nav (a list
     of links like /en/race/6-hours-of-imola-2026) - fetch the homepage
     once and pull every "-{year}" race link out of it. This also
     naturally picks up mid-season calendar revisions (round added,
     removed, or rescheduled) since it's reading the live nav, not a
     hardcoded round list.
  2. Fetch each race's own page (e.g. /en/race/6-hours-of-imola-2026),
     which has a real per-session timetable: a date header ("April
     17th") followed by session name / time pairs ("Free Practice 1" /
     "10:15 AM", or "Free Practice 1" / "TBC" before times are
     announced). Only sessions with a real time are emitted - "TBC"
     sessions are skipped rather than guessed at, so nothing gets a
     fabricated timestamp; they'll show up automatically once the site
     publishes a real time and the scraper next runs.

Session times on fiawec.com are shown in the circuit's local time, so a
per-circuit timezone (TRACK_TIMEZONES below) is needed to convert to UTC.

Previous version of this script fell back to a hardcoded "known 2026
schedule" when live scraping failed or returned 0 events - useful in
principle, but it had already gone stale (assumed Qatar/Bahrain closed
out the season; the live calendar was revised again since to close with
Barcelona/Monza instead) and silently wrote wrong data indistinguishable
from a real scrape. Rather than maintain a second calendar that can drift
from reality, this version has no calendar fallback: if the live scrape
fails, it aborts (via common.write_output's min_events check) instead of
writing stale data.

Run this from the repo root: python scripts/wec_schedule_scraper.py
"""

import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HEADERS, fetch, slugify, make_unique_id_assigner, write_output  # noqa: E402

SEASON_YEAR = 2026  # bump each year
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "wec" / f"{SEASON_YEAR}.json"

HOMEPAGE_URL = "https://www.fiawec.com/"
RACE_LINK_RE = re.compile(rf'href="(/en/race/[a-z0-9-]+-{SEASON_YEAR})"')

DATE_HEADER_RE = re.compile(r'^([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)$')
TIME_RE = re.compile(r'^(\d{1,2}):(\d{2})\s*(AM|PM)$', re.IGNORECASE)
MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
}

# fiawec.com shows session times in the circuit's local time - matched
# against the race URL slug (substring, checked in order). Add new
# circuits here if the calendar changes; anything unmatched is skipped
# with a warning rather than guessing a timezone.
TRACK_TIMEZONES = [
    ("lone-star-le-mans", "America/Chicago"),  # Circuit of the Americas, Austin - must precede "le-mans" below
    ("imola", "Europe/Rome"),
    ("monza", "Europe/Rome"),
    ("spa-francorchamps", "Europe/Brussels"),
    ("le-mans", "Europe/Paris"),
    ("sao-paulo", "America/Sao_Paulo"),
    ("fuji", "Asia/Tokyo"),
    ("barcelona", "Europe/Madrid"),
    ("qatar", "Asia/Qatar"),
    ("bahrain", "Asia/Bahrain"),
]


def find_track_timezone(slug: str) -> ZoneInfo | None:
    for keyword, tz_name in TRACK_TIMEZONES:
        if keyword in slug:
            return ZoneInfo(tz_name)
    return None


def discover_race_urls() -> list[str]:
    """Every /en/race/...-{year} link on the homepage - this is the site's
    own live calendar nav, so it reflects the current (possibly revised)
    round list rather than a list we maintain by hand."""
    html = fetch(HOMEPAGE_URL)
    paths = sorted(set(RACE_LINK_RE.findall(html)))
    return [f"https://www.fiawec.com{path}" for path in paths]


def parse_race_page(html: str) -> tuple[str, list[dict]]:
    """Returns (event_name, sessions) for one race page, where sessions is
    [{"name": "Free Practice 1", "month": 4, "day": 17, "hour": 10,
    "minute": 15}, ...] in local (circuit) time - only for sessions with
    a real time; "TBC" sessions are skipped."""
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    event_name = title_tag.get_text(strip=True) if title_tag else "WEC Race"
    event_name = re.sub(rf"\s*{SEASON_YEAR}\s*$", "", event_name).strip()

    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]

    sessions = []
    current_month = current_day = None
    in_timetable = False
    i = 0
    while i < len(lines):
        line = lines[i]

        date_match = DATE_HEADER_RE.match(line)
        if date_match:
            in_timetable = True
            month_name, day_text = date_match.groups()
            month = MONTHS.get(month_name.lower())
            if month:
                current_month, current_day = month, int(day_text)
            i += 1
            continue

        if line == "Track info":  # end of the session timetable
            break

        if in_timetable and current_month is not None:
            # Expect: session name line, then a time-or-TBC line next.
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                time_match = TIME_RE.match(next_line)
                if time_match:
                    hour, minute, meridiem = time_match.groups()
                    hour = int(hour) % 12
                    if meridiem.upper() == "PM":
                        hour += 12
                    sessions.append({
                        "name": line,
                        "month": current_month,
                        "day": current_day,
                        "hour": hour,
                        "minute": int(minute),
                    })
                    i += 2
                    continue
                if next_line.upper().startswith("TBC"):
                    i += 2  # known session, time not announced yet - skip
                    continue

        i += 1

    return event_name, sessions


def build_event_entries(event_name: str, sessions: list[dict], track_tz: ZoneInfo) -> list[dict]:
    event_slug = slugify(event_name)
    assign_id = make_unique_id_assigner()
    entries = []
    for s in sessions:
        local_dt = datetime(SEASON_YEAR, s["month"], s["day"], s["hour"], s["minute"], tzinfo=track_tz)
        utc_iso = local_dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        session_slug = slugify(s["name"])
        entries.append({
            "id": assign_id(f"wec-{SEASON_YEAR}-{event_slug}-{session_slug}"),
            "weekend": event_name,
            "name": s["name"],
            "utc": utc_iso,
        })
    return entries


def scrape() -> list[dict]:
    print("Discovering race URLs from fiawec.com...", file=sys.stderr)
    race_urls = discover_race_urls()
    print(f"Found {len(race_urls)} races for {SEASON_YEAR}", file=sys.stderr)

    all_events = []
    for i, url in enumerate(race_urls, 1):
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        try:
            html = fetch(url)
        except requests.RequestException as err:
            print(f"  [{i}/{len(race_urls)}] Failed to fetch {url}: {err}", file=sys.stderr)
            continue

        event_name, sessions = parse_race_page(html)

        track_tz = find_track_timezone(slug)
        if track_tz is None:
            print(f"  [{i}/{len(race_urls)}] {event_name}: no known timezone for slug '{slug}', skipping", file=sys.stderr)
            continue

        entries = build_event_entries(event_name, sessions, track_tz)
        print(f"  [{i}/{len(race_urls)}] {event_name}: {len(entries)} session(s) with confirmed times", file=sys.stderr)
        all_events.extend(entries)

    return all_events


def main():
    events = scrape()
    events.sort(key=lambda e: e["utc"])

    output = {
        "sportKey": "wec",
        "season": str(SEASON_YEAR),
        "events": events,
    }
    write_output(OUTPUT_PATH, output, min_events=1)


if __name__ == "__main__":
    main()
