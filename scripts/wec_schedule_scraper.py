#!/usr/bin/env python3
"""
WEC (FIA World Endurance Championship) schedule scraper for the
sportocal-data repo. Writes motorsport/wec/2026.json.

WHY THIS SCRIPT USES A HEADLESS BROWSER (unlike every other scraper in
this repo): fiawec.com's race pages (/en/race/{slug}-{year}) render their
entire session timetable client-side via JS after page load - the raw
HTML `requests.get` receives literally shows "Loading..." where the
timetable goes. This was tried twice and failed both times against a
live run:
  1. First attempt scraped the timetable widget directly - 0 sessions
     for every race, including races that had already finished.
  2. Second attempt tried to route around that by fetching each race's
     official "Timetable" PDF instead (a document linked from the same
     page) - but the *link itself* lives in a JS-hydrated section too,
     so plain HTTP never found the PDF URL either.
Both the widget and the section that links to the PDF are behind the
same client-side rendering, so there's no plain-HTTP path into this
site's per-race schedule data at all. A real render is required.

The homepage's calendar nav is the one part of the site that *is*
server-rendered (this worked correctly in both earlier attempts - race
URL discovery never failed), so that part still uses a plain request.

Run this from the repo root: python scripts/wec_schedule_scraper.py
Requires Playwright's Chromium browser to be installed:
  playwright install --with-deps chromium
"""

import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import fetch, slugify, make_unique_id_assigner, write_output  # noqa: E402

SEASON_YEAR = 2026  # bump each year
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "wec" / f"{SEASON_YEAR}.json"

HOMEPAGE_URL = "https://www.fiawec.com/"
RACE_HREF_RE = re.compile(rf"^/en/race/[a-z0-9-]+-{SEASON_YEAR}$")

DATE_HEADER_RE = re.compile(r'^([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)$')
TIME_RE = re.compile(r'^(\d{1,2}):(\d{2})\s*(AM|PM)$', re.IGNORECASE)
MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
}

# fiawec.com shows session times in the circuit's local time - matched
# against the race URL slug (substring, checked in order - more specific
# entries first so e.g. "lone-star-le-mans" doesn't get caught by the
# generic "le-mans" rule).
TRACK_TIMEZONES = [
    ("lone-star-le-mans", "America/Chicago"),  # Circuit of the Americas, Austin
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
    """Every /en/race/...-{year} link on the (server-rendered) homepage."""
    html = fetch(HOMEPAGE_URL)
    soup = BeautifulSoup(html, "html.parser")
    slugs_seen = set()
    urls = []
    for link in soup.find_all("a", href=RACE_HREF_RE):
        if link["href"] not in slugs_seen:
            slugs_seen.add(link["href"])
            urls.append(f"https://www.fiawec.com{link['href']}")
    return urls


def render_race_page_html(page, url: str) -> str:
    """Loads a race page in the given Playwright page and waits for the
    timetable to actually render before returning the HTML. "Track info"
    is the heading immediately after the timetable on every race page, so
    waiting for it is a reliable signal the async content has loaded."""
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_selector("text=Track info", timeout=15000)
    except PlaywrightTimeoutError:
        pass  # fall through and parse whatever did load - parse_race_page handles empty results
    return page.content()


def parse_race_page(html: str) -> tuple[str, list[dict]]:
    """Returns (event_name, sessions) for one *rendered* race page, where
    sessions is [{"name": "Free Practice 1", "month": 4, "day": 17,
    "hour": 10, "minute": 15}, ...] in local (circuit) time - only for
    sessions with a real time; "TBC" sessions are skipped rather than
    guessed at."""
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

        if in_timetable and current_month is not None and i + 1 < len(lines):
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
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        for i, url in enumerate(race_urls, 1):
            slug = url.rstrip("/").rsplit("/", 1)[-1]
            track_tz = find_track_timezone(slug)
            if track_tz is None:
                print(f"  [{i}/{len(race_urls)}] {slug}: no known timezone, skipping", file=sys.stderr)
                continue

            try:
                html = render_race_page_html(page, url)
            except Exception as err:
                print(f"  [{i}/{len(race_urls)}] Failed to render {url}: {err}", file=sys.stderr)
                continue

            event_name, sessions = parse_race_page(html)
            entries = build_event_entries(event_name, sessions, track_tz)
            print(f"  [{i}/{len(race_urls)}] {event_name}: {len(entries)} session(s) with confirmed times", file=sys.stderr)
            all_events.extend(entries)

        browser.close()

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
