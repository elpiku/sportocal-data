#!/usr/bin/env python3
"""
NASCAR Craftsman Truck Series schedule scraper for the sportocal-data repo.

Same two-source architecture as nascar_cup.py - see that script's
docstring for the full reasoning behind it:

  - Jayski's per-weekend "Official Event Schedule" PDFs (linked from
    jayski.com/nascar-weekend-schedules/2026-nascar-weekend-event-schedules/)
    are NASCAR's own official weekend timing sheets, listing every
    series racing that weekend. This pulls out only the "NCTS" (NASCAR
    Craftsman Truck Series) rows.

  - Jayski's Truck Series schedule table supplies the official race
    title (e.g. "Fresh From Florida 250") for each weekend - the PDFs
    themselves don't include the sponsor race name, just track name and
    session times.

Unlike nascar_cup.py, this has no season-wide fallback source: ESPN's
racing API doesn't expose a separate Truck Series league in the same
shape as its NASCAR Cup one, and rather than guess at an unverified
endpoint, this just aborts loudly (via common.write_output's min_events
check) if the Jayski pipeline fails, instead of risking silent wrong
data from an untested fallback.

Run this from the repo root: python scripts/nascar_truck.py
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
from common import HEADERS, fetch, fetch_bytes, slugify, make_unique_id_assigner, write_output  # noqa: E402

SEASON_YEAR = 2026  # bump each year
SERIES_TAG = "NCTS"
ID_PREFIX = "ncts"
SPORT_KEY = "nascar-craftsman"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "nascar" / "craftsman" / f"{SEASON_YEAR}.json"

JAYSKI_WEEKENDS_INDEX_URL = "https://www.jayski.com/nascar-weekend-schedules/2026-nascar-weekend-event-schedules/"
JAYSKI_SCHEDULE_URL = f"https://www.jayski.com/truck-series/{SEASON_YEAR}-nascar-craftsman-truck-series-schedule/"

ET_TZ = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

MONTH_MAP = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}
JAYSKI_SCHEDULE_DATE_RE = re.compile(r"([A-Za-z]{3,9})\.?,?\s+(\d{1,2})")

# One event-schedule PDF weekend line, e.g.:
#   "1:00 PM 1:50 PM NCTS PRACTICE TRACK HOT"
#   "2:05 PM 3:00 PM NCTS QUALIFYING (IMPOUND) TRACK HOT"
#   "7:30 PM NCTS RACE (STAGES 70/140/250 LAPS = 187.5 MILES) TRACK HOT"
# Anchored so the event text must *start* with one of these keywords -
# this is what keeps admin rows (garage hours, driver meetings, etc.)
# from being mistaken for a real session.
PDF_TIME = r"(\d{1,2}:\d{2}\s*(?:AM|PM))"
PDF_LINE_RE = re.compile(
    rf"^{PDF_TIME}(?:\s+{PDF_TIME})?\s+(?:Approx\.?\s+)?{SERIES_TAG}\s+"
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
    """Scrapes the weekend-schedules index page for every Truck-series
    weekend's PDF URL. Skips weekends where NCTS isn't listed among the
    series racing that weekend."""
    html = fetch(JAYSKI_WEEKENDS_INDEX_URL)
    soup = BeautifulSoup(html, "html.parser")

    weekend_page_urls = []
    for li in soup.find_all("li"):
        text = li.get_text(" ", strip=True)
        a = li.find("a", href=True)
        if not a or "event-schedule" not in a["href"]:
            continue
        if SERIES_TAG not in text:  # this weekend isn't a Truck race
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
    reader = PdfReader(BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return parse_schedule_text(text)


def parse_schedule_text(text: str) -> list[dict]:
    """Extracts every {SERIES_TAG} practice/qualifying/race session from
    one weekend's event-schedule text. Returns [{"session_key": ...,
    "display_name": ..., "month": int, "day": int, "hour": int,
    "minute": int}, ...] in local (Eastern) track time."""
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
        base_id = f"{ID_PREFIX}-{SEASON_YEAR}-{slugify(weekend_name)}-{s['session_key']}"
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
    print(f"Found {len(pdf_urls)} Truck-series weekend PDFs", file=sys.stderr)

    events = []
    for pdf_url in pdf_urls:
        try:
            pdf_bytes = fetch_bytes(pdf_url)
        except requests.RequestException as err:
            print(f"  Failed to fetch PDF {pdf_url}: {err}", file=sys.stderr)
            continue

        try:
            sessions = parse_pdf_sessions(pdf_bytes)
        except Exception as err:  # malformed/unreadable PDF shouldn't kill the run
            print(f"  Failed to parse PDF {pdf_url}: {err}", file=sys.stderr)
            continue

        events.extend(build_weekend_events(sessions, jayski_titles))

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
    events.sort(key=lambda e: e["utc"])

    output = {
        "sportKey": SPORT_KEY,
        "season": str(SEASON_YEAR),
        "events": events,
    }
    write_output(OUTPUT_PATH, output, min_events=5)


if __name__ == "__main__":
    main()
