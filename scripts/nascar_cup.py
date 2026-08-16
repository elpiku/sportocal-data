#!/usr/bin/env python3
"""
NASCAR Cup Series schedule scraper for the sportocal-data repo.

Three sources, three different jobs:

  - Jayski's per-weekend "Official Event Schedule" PDFs (linked from
    jayski.com/nascar-weekend-schedules/2026-nascar-weekend-event-schedules/)
    are NASCAR's own official weekend timing sheets and are the *only* one
    of the four originally-considered sources that actually lists practice
    and qualifying times, not just the race. They're real, minute-by-minute
    schedules covering every series racing that weekend (Cup, O'Reilly,
    Trucks, ARCA, ...) so this script pulls out only the "NCS" (NASCAR Cup
    Series) rows.

  - Jayski's main schedule table (already used before) is kept around
    only to supply the official race title (e.g. "Autotrader 400") for
    each weekend - the PDFs themselves don't include the sponsor race
    name, just track name and session times.

  - ESPN's Core API is kept as a season-wide fallback: if the PDF
    pipeline comes back with nothing at all (e.g. Jayski's page structure
    changes), this falls back to ESPN for race-only events, same as the
    previous version of this script. It cannot supply practice/qualifying
    since ESPN's NASCAR feed doesn't expose separate sessions.

Two other sources were considered and dropped entirely - see the notes
above the JAYSKI_* URLs below.

Run this from the repo root: python scripts/nascar_cup.py
"""

import re
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from pypdf import PdfReader
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HEADERS, fetch, slugify, make_unique_id_assigner, write_output  # noqa: E402

SEASON_YEAR = 2026  # bump each year
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "nascar" / "cup" / f"{SEASON_YEAR}.json"

# Lists every race weekend of the season with links to each weekend's
# event-schedule page (which in turn links to the actual PDF).
JAYSKI_WEEKENDS_INDEX_URL = "https://www.jayski.com/nascar-weekend-schedules/2026-nascar-weekend-event-schedules/"
# The season-at-a-glance table; scraped only for official race titles.
JAYSKI_SCHEDULE_URL = f"https://www.jayski.com/nascar-cup-series/{SEASON_YEAR}-nascar-cup-series-schedule/"

# motorsport.com/nascar-cup/schedule/2026 and nascar.com/nascar-cup-series/
# 2026/schedule were both considered but dropped: both render their
# schedule tables client-side via JS after page load, so the server HTML
# contains no event data to scrape (motorsport.com ships bare column
# headers like "PRACTICE 1"/"QUALIFYING"/"RACE" with no rows; nascar.com
# literally ships the text "Loading race information...").

ESPN_CORE_API_URL = (
    f"https://sports.core.api.espn.com/v2/sports/racing/leagues/nascar-premier/"
    f"seasons/{SEASON_YEAR}/types/2/events?limit=100"
)

ET_TZ = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

MONTH_MAP = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}
JAYSKI_SCHEDULE_DATE_RE = re.compile(r"([A-Za-z]{3,9})\.?,?\s+(\d{1,2})")

# One event-schedule PDF weekend line, e.g.:
#   "3:30 PM 4:30 PM NCS PRACTICE TRACK HOT"
#   "4:40 PM 5:30 PM NCS QUALIFYING (IMPOUND) TRACK HOT"
#   "7:00 PM NCS QUALIFYING RACE 1 (60 LAPS, 150 MILES) TRACK HOT"   <- a Duel
#   "1:30 PM NCS RACE (STAGES 65/130/200 LAPS = 500 MILES) TRACK HOT"
# Anchored so the event text must *start* with one of these keywords -
# this is what keeps admin rows like "NCS RANDOM DRAWING (QUALIFYING
# LINEUP) (VIRTUAL)" from being mistaken for a qualifying session.
PDF_TIME = r"(\d{1,2}:\d{2}\s*(?:AM|PM))"
PDF_LINE_RE = re.compile(
    rf"^{PDF_TIME}(?:\s+{PDF_TIME})?\s+(?:Approx\.?\s+)?NCS\s+"
    rf"(PRACTICE(?:\s+\d+)?|QUALIFYING\s+RACE\s+\d+|QUALIFYING(?:\s*\(IMPOUND\))?|RACE)\b"
)
PDF_DATE_HEADER_RE = re.compile(
    r"^[A-Z]+,\s+([A-Z]+)\s+(\d{1,2})$"
)  # e.g. "SATURDAY, AUGUST 15"


def fetch_jayski_titles() -> dict[tuple[int, int], str]:
    """Scrapes Jayski's main schedule table -> {(month, day): official race
    title}. Skips off weeks (no linked race name) and non-date rows."""
    html = fetch(JAYSKI_SCHEDULE_URL)
    soup = BeautifulSoup(html, "html.parser")

    titles = {}
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        date_match = JAYSKI_SCHEDULE_DATE_RE.search(cells[1].get_text(" ", strip=True))
        if not date_match:
            continue
        mon_text, day_text = date_match.groups()
        month = next((v for k, v in MONTH_MAP.items() if k.startswith(mon_text[:3].title())), None)
        if not month:
            continue

        title = cells[2].get_text(strip=True)
        if not title or "OFF WEEK" in row.get_text(" ", strip=True).upper():
            continue

        titles[(month, int(day_text))] = title

    return titles


def fetch_weekend_pdf_urls() -> list[str]:
    """Scrapes the weekend-schedules index page for every Cup-series
    weekend's PDF URL. Skips weekends where NCS isn't listed among the
    series racing that weekend (e.g. Truck/O'Reilly-only off-weeks for
    Cup, like Rockingham or St. Petersburg)."""
    html = fetch(JAYSKI_WEEKENDS_INDEX_URL)
    soup = BeautifulSoup(html, "html.parser")

    weekend_page_urls = []
    for li in soup.find_all("li"):
        text = li.get_text(" ", strip=True)
        a = li.find("a", href=True)
        if not a or "event-schedule" not in a["href"]:
            continue
        if "NCS" not in text:  # this weekend isn't a Cup race
            continue
        weekend_page_urls.append(a["href"])

    pdf_urls = []
    for page_url in weekend_page_urls:
        try:
            page_html = fetch(page_url)
        except requests.RequestException as err:
            print(f"  Failed to fetch weekend page {page_url}: {err}", file=sys.stderr)
            continue
        page_soup = BeautifulSoup(page_html, "html.parser")
        pdf_link = page_soup.find("a", href=re.compile(r"\.pdf$"))
        if pdf_link:
            pdf_urls.append(pdf_link["href"])
        else:
            print(f"  No PDF link found on {page_url}", file=sys.stderr)

    return pdf_urls


def parse_pdf_sessions(pdf_bytes: bytes) -> list[dict]:
    """Extracts every NCS practice/qualifying/race session from one
    weekend's event-schedule PDF (see parse_schedule_text for the parsing
    logic itself, kept separate so it's testable without a real PDF)."""
    reader = PdfReader(BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return parse_schedule_text(text)


def parse_schedule_text(text: str) -> list[dict]:
    """Extracts every NCS practice/qualifying/race session from one
    weekend's event-schedule text (as extracted from the official PDF).
    Returns [{"session_key": ..., "display_name": ..., "month": int,
    "day": int, "hour": int, "minute": int}, ...] in local (Eastern) track
    time - conversion to UTC happens later, once we know the actual year
    (the PDF only gives month/day, no year)."""
    sessions = []
    current_month = current_day = None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        date_header = PDF_DATE_HEADER_RE.match(line)
        if date_header:
            mon_text, day_text = date_header.groups()
            month = next((v for k, v in MONTH_MAP.items() if k.upper() == mon_text), None)
            if month:
                current_month, current_day = month, int(day_text)
            continue

        match = PDF_LINE_RE.match(line)
        if not match or current_month is None:
            continue

        start_time, _end_time, keyword = match.groups()
        session_key, display_name = classify_pdf_keyword(keyword)

        dt = datetime.strptime(start_time.replace(" ", ""), "%I:%M%p")
        sessions.append({
            "session_key": session_key,
            "display_name": display_name,
            "month": current_month,
            "day": current_day,
            "hour": dt.hour,
            "minute": dt.minute,
        })

    return sessions


def classify_pdf_keyword(keyword: str) -> tuple[str, str]:
    """PDF event keyword (e.g. "PRACTICE 2", "QUALIFYING RACE 1",
    "QUALIFYING (IMPOUND)", "RACE") -> (id slug, repo display name)."""
    k = keyword.upper().strip()

    duel_match = re.match(r"QUALIFYING\s+RACE\s+(\d+)", k)
    if duel_match:
        return "duels", f"Duel #{duel_match.group(1)}"

    practice_match = re.match(r"PRACTICE(?:\s+(\d+))?", k)
    if practice_match:
        num = practice_match.group(1)
        return (f"fp{num}" if num else "fp1"), (f"Practice {num}" if num else "Practice")

    if k.startswith("QUALIFYING"):
        return "qualifying", "Qualifying"

    return "race", "Race"  # only remaining branch per PDF_LINE_RE


def build_weekend_events(pdf_sessions: list[dict], jayski_titles: dict) -> list[dict]:
    """Turns one weekend's parsed PDF sessions into this repo's event
    schema, resolving the official race title via the (month, day) of
    the weekend's "race" session."""
    if not pdf_sessions:
        return []

    race_sessions = [s for s in pdf_sessions if s["session_key"] == "race"]
    race_date = race_sessions[0] if race_sessions else pdf_sessions[0]
    weekend_name = jayski_titles.get((race_date["month"], race_date["day"]))
    if not weekend_name:
        return []  # can't confidently name this weekend - skip rather than guess

    assign_id = make_unique_id_assigner()
    events = []
    for s in pdf_sessions:
        local_dt = datetime(SEASON_YEAR, s["month"], s["day"], s["hour"], s["minute"], tzinfo=ET_TZ)
        utc_iso = local_dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        base_id = f"cup-{SEASON_YEAR}-{slugify(weekend_name)}-{s['session_key']}"
        events.append({
            "id": assign_id(base_id),
            "weekend": weekend_name,
            "name": s["display_name"],
            "utc": utc_iso,
        })
    return events


def fetch_pdf_based_events(jayski_titles: dict) -> list[dict]:
    print("Fetching weekend PDF schedule links from Jayski...", file=sys.stderr)
    pdf_urls = fetch_weekend_pdf_urls()
    print(f"Found {len(pdf_urls)} Cup-series weekend PDFs", file=sys.stderr)

    events = []
    for pdf_url in pdf_urls:
        try:
            res = requests.get(pdf_url, headers=HEADERS, timeout=20)
            res.raise_for_status()
        except requests.RequestException as err:
            print(f"  Failed to fetch PDF {pdf_url}: {err}", file=sys.stderr)
            continue

        try:
            sessions = parse_pdf_sessions(res.content)
        except Exception as err:  # malformed/unreadable PDF shouldn't kill the run
            print(f"  Failed to parse PDF {pdf_url}: {err}", file=sys.stderr)
            continue

        events.extend(build_weekend_events(sessions, jayski_titles))

    return events


# --- ESPN fallback (used only if the PDF pipeline yields nothing) ---------

def to_utc_iso(date_str: str) -> str | None:
    if not date_str:
        return None
    d = date_str.strip()
    if d.endswith("Z"):
        d = d[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(d)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_espn_fallback_events(jayski_titles: dict) -> list[dict]:
    print("PDF pipeline produced nothing - falling back to ESPN (race-only)...", file=sys.stderr)
    res = requests.get(ESPN_CORE_API_URL, headers=HEADERS, timeout=15)
    res.raise_for_status()
    items = res.json().get("items", [])

    assign_id = make_unique_id_assigner()
    events = []
    for item in items:
        event_url = item.get("$ref") if isinstance(item, dict) else item
        if not event_url:
            continue
        try:
            ev_res = requests.get(event_url, headers=HEADERS, timeout=10)
            if ev_res.status_code != 200:
                continue
            ev = ev_res.json()
        except requests.RequestException:
            continue

        utc_iso = to_utc_iso(ev.get("date"))
        if not utc_iso:
            continue
        espn_name = ev.get("name") or ev.get("shortName") or "NASCAR Cup Race"

        local_dt = datetime.strptime(utc_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).astimezone(ET_TZ)
        weekend_name = jayski_titles.get((local_dt.month, local_dt.day), espn_name)

        base_id = f"cup-{SEASON_YEAR}-{slugify(weekend_name)}-race"
        events.append({
            "id": assign_id(base_id),
            "weekend": weekend_name,
            "name": "Race",
            "utc": utc_iso,
        })

    return events


def main():
    print("Fetching official race titles from Jayski...", file=sys.stderr)
    try:
        jayski_titles = fetch_jayski_titles()
    except requests.RequestException as err:
        print(f"Jayski title fetch failed ({err})", file=sys.stderr)
        jayski_titles = {}
    print(f"Got {len(jayski_titles)} titled dates", file=sys.stderr)

    events = fetch_pdf_based_events(jayski_titles)
    print(f"Parsed {len(events)} sessions from PDFs", file=sys.stderr)

    if not events:
        events = fetch_espn_fallback_events(jayski_titles)

    events.sort(key=lambda e: e["utc"])

    output = {
        "sportKey": "nascar-cup",
        "season": str(SEASON_YEAR),
        "events": events,
    }
    write_output(OUTPUT_PATH, output, min_events=5)


if __name__ == "__main__":
    main()
