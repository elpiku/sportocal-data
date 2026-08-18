#!/usr/bin/env python3
"""
WEC (FIA World Endurance Championship) schedule scraper for the
sportocal-data repo. Writes motorsport/wec/2026.json.

IMPORTANT LESSON FROM THE PREVIOUS VERSION OF THIS SCRIPT: fiawec.com's
per-race page (e.g. /en/race/6-hours-of-imola-2026) *looks* like it has a
full session timetable when fetched normally - but that block is
JS-hydrated after page load (it literally shows "Loading..." first) and
plain `requests.get` never receives it. A live run of the previous
version confirmed this: every single race, including ones already
finished, came back with 0 sessions. Fetching the page with a real
browser (which is how that version was developed and tested) masked the
problem entirely, since a browser executes the JS and a plain HTTP
client doesn't.

This version avoids the JS-hydrated widget entirely and instead scrapes
each race's official "Timetable" PDF document (linked from the same
page, e.g. /en/race/document/download/2304) - a real static file, so a
plain HTTP GET gets the whole thing.

Two-step scrape:

  1. The homepage's calendar nav *is* server-rendered (this part worked
     fine in the previous version - URL discovery succeeded even when
     session-scraping didn't) - fetch it once for every race URL plus
     each race's day/month, which doubles as the event's *last* calendar
     day (see step 2).
  2. Fetch each race page (still plain HTML - just not the timetable
     widget) for its title and its "Timetable" PDF link, then fetch and
     parse that PDF. The PDF lists every series' full multi-day schedule
     (Cup... no, WEC/support races) as one continuous, chronologically
     ordered stream of "HH:MM [HH:MM] <series> <event> <location>" lines
     with no day headers on the actual session rows (the day names only
     appear in an unrelated summary block elsewhere in the PDF, not
     aligned with the rows) - so calendar days are inferred from the
     rows themselves: whenever a row's start time is earlier than the
     previous row's, that's a rollover to the next calendar day. Only
     "FIA WEC" rows for Free Practice / Qualifying / Race are kept
     (everything else - scrutineering, drivers' briefings, other
     series - is noise); the remaining blocks of real sessions are
     assigned calendar dates by counting backward from the race's known
     final day (from step 1), since practice/qualifying/race always run
     on the event's last consecutive days with no gap.

Run this from the repo root: python scripts/wec_schedule_scraper.py
"""

import re
import sys
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from pypdf import PdfReader
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HEADERS, fetch, slugify, make_unique_id_assigner, write_output  # noqa: E402

SEASON_YEAR = 2026  # bump each year
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "motorsport" / "wec" / f"{SEASON_YEAR}.json"

HOMEPAGE_URL = "https://www.fiawec.com/"
RACE_HREF_RE = re.compile(rf"^/en/race/[a-z0-9-]+-{SEASON_YEAR}$")
# A "DD Mon" pair as it would appear in actual rendered text near a race
# link (e.g. "ITA 19 Apr") - deliberately simple since this is applied to
# BeautifulSoup's get_text() output (visible text only), not raw HTML, so
# it can't accidentally match text inside tag/class attributes.
NAV_DATE_RE = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3})\b")

MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
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

# One PDF timetable row, e.g.:
#   "10:15 11:45 FIA WEC FREE PRACTICE 1 Track 90'"
#   "14:50 15:00 FIA WEC QUALIFYING - HYPERPOLE LMGT3 Track 10'"
#   "13:00 19:00 FIA WEC RACE - Rolling Start RACE 5 6h"
# Anchored so the event text must start with one of these keywords right
# after "FIA WEC" - this is what keeps the hundreds of admin/other-series
# rows (scrutineering, drivers' briefings, support-race sessions) out.
PDF_TIME = r"(\d{2}):(\d{2})"
PDF_LINE_RE = re.compile(
    rf"^{PDF_TIME}(?:\s+{PDF_TIME})?\s+FIA WEC\s+"
    rf"(FREE PRACTICE\s*\d*|QUALIFYING\s*-\s*HYPERPOLE\s+[A-Z0-9]+|QUALIFYING\s*-\s*[A-Z0-9]+|RACE\b)"
)
ANY_TIME_LINE_RE = re.compile(r"^(\d{2}):(\d{2})")


def find_track_timezone(slug: str) -> ZoneInfo | None:
    for keyword, tz_name in TRACK_TIMEZONES:
        if keyword in slug:
            return ZoneInfo(tz_name)
    return None


def discover_races() -> list[dict]:
    """Every race on the homepage nav -> {"url", "slug", "last_day": date}.
    "last_day" is the single day/month shown next to the link in the nav
    (the race day itself, i.e. the event's final calendar day) - used
    later to anchor the PDF's day-rollover blocks to real calendar dates.
    Walks up from each race link to the nearest ancestor that contains a
    "DD Mon" text pair, rather than guessing a fixed DOM depth."""
    html = fetch(HOMEPAGE_URL)
    soup = BeautifulSoup(html, "html.parser")

    races = {}
    for link in soup.find_all("a", href=RACE_HREF_RE):
        slug = link["href"].rsplit("/", 1)[-1]
        if slug in races:
            continue

        date_match = None
        container = link
        for _ in range(6):  # walk up a few ancestor levels looking for the date text
            container = container.find_parent()
            if container is None:
                break
            date_match = NAV_DATE_RE.search(container.get_text(" ", strip=True))
            if date_match:
                break

        if not date_match:
            print(f"  WARNING: no nav date found near {link['href']}, skipping", file=sys.stderr)
            continue

        day_text, mon_text = date_match.groups()
        month = MONTHS.get(mon_text.lower()[:3])
        if not month:
            continue

        races[slug] = {
            "url": f"https://www.fiawec.com{link['href']}",
            "slug": slug,
            "last_day": date(SEASON_YEAR, month, int(day_text)),
        }

    return list(races.values())


def find_timetable_pdf_url(race_page_html: str) -> str | None:
    soup = BeautifulSoup(race_page_html, "html.parser")
    link = soup.find("a", string=re.compile(r"^\s*Timetable\s*$"))
    if not link or not link.get("href"):
        return None
    href = link["href"]
    return href if href.startswith("http") else f"https://www.fiawec.com{href}"


def classify_wec_keyword(keyword: str) -> tuple[str, str]:
    k = keyword.upper().strip()

    practice_match = re.match(r"FREE PRACTICE\s*(\d+)?", k)
    if k.startswith("FREE PRACTICE"):
        num = practice_match.group(1)
        return (f"fp{num}" if num else "fp1"), (f"Free Practice {num}" if num else "Free Practice")

    hyperpole_match = re.match(r"QUALIFYING\s*-\s*HYPERPOLE\s+([A-Z0-9]+)", k)
    if hyperpole_match:
        cls = hyperpole_match.group(1)
        return f"hyperpole-{slugify(cls)}", f"Hyperpole - {cls}"

    qualifying_match = re.match(r"QUALIFYING\s*-\s*([A-Z0-9]+)", k)
    if qualifying_match:
        cls = qualifying_match.group(1)
        return f"qualifying-{slugify(cls)}", f"Qualifying - {cls}"

    return "race", "Race"  # only remaining branch per PDF_LINE_RE


def parse_pdf_timetable(text: str, last_day: date) -> list[dict]:
    """Extracts FIA WEC Free Practice / Qualifying / Race rows from the raw
    PDF text and assigns each a real calendar date, working backward from
    the event's known final day. Returns [{"name", "utc_date", "hour",
    "minute"}, ...] in local (circuit) time."""
    blocks: list[list[dict]] = [[]]
    prev_start_minutes = None

    for line in text.splitlines():
        line = line.strip()
        time_match = ANY_TIME_LINE_RE.match(line)
        if not time_match:
            continue

        start_minutes = int(time_match.group(1)) * 60 + int(time_match.group(2))
        if prev_start_minutes is not None and start_minutes < prev_start_minutes:
            blocks.append([])  # a start time earlier than the previous row = new day
        prev_start_minutes = start_minutes

        session_match = PDF_LINE_RE.match(line)
        if session_match:
            hour, minute, _eh, _em, keyword = session_match.groups()
            session_key, display_name = classify_wec_keyword(keyword)
            blocks[-1].append({
                "session_key": session_key,
                "name": display_name,
                "hour": int(hour),
                "minute": int(minute),
            })

    session_blocks = [b for b in blocks if b]  # drop admin-only days with no FIA WEC target sessions
    dated_sessions = []
    for i, block in enumerate(session_blocks):
        day_offset = len(session_blocks) - 1 - i
        block_date = last_day - timedelta(days=day_offset)
        for s in block:
            dated_sessions.append({**s, "date": block_date})
    return dated_sessions


def build_event_entries(event_name: str, sessions: list[dict], track_tz: ZoneInfo) -> list[dict]:
    event_slug = slugify(event_name)
    assign_id = make_unique_id_assigner()
    entries = []
    for s in sessions:
        local_dt = datetime(
            s["date"].year, s["date"].month, s["date"].day, s["hour"], s["minute"], tzinfo=track_tz
        )
        utc_iso = local_dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        entries.append({
            "id": assign_id(f"wec-{SEASON_YEAR}-{event_slug}-{s['session_key']}"),
            "weekend": event_name,
            "name": s["name"],
            "utc": utc_iso,
        })
    return entries


def scrape() -> list[dict]:
    print("Discovering races from fiawec.com homepage nav...", file=sys.stderr)
    races = discover_races()
    print(f"Found {len(races)} races for {SEASON_YEAR}", file=sys.stderr)

    all_events = []
    for i, race in enumerate(races, 1):
        track_tz = find_track_timezone(race["slug"])
        if track_tz is None:
            print(f"  [{i}/{len(races)}] {race['slug']}: no known timezone, skipping", file=sys.stderr)
            continue

        try:
            page_html = fetch(race["url"])
        except requests.RequestException as err:
            print(f"  [{i}/{len(races)}] Failed to fetch {race['url']}: {err}", file=sys.stderr)
            continue

        title_tag = BeautifulSoup(page_html, "html.parser").find("title")
        event_name = title_tag.get_text(strip=True) if title_tag else race["slug"]
        event_name = re.sub(rf"\s*{SEASON_YEAR}\s*$", "", event_name).strip()

        pdf_url = find_timetable_pdf_url(page_html)
        if not pdf_url:
            print(f"  [{i}/{len(races)}] {event_name}: no Timetable PDF link found, skipping", file=sys.stderr)
            continue

        try:
            pdf_res = requests.get(pdf_url, headers=HEADERS, timeout=20)
            pdf_res.raise_for_status()
            reader = PdfReader(BytesIO(pdf_res.content))
            pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as err:
            print(f"  [{i}/{len(races)}] {event_name}: failed to fetch/parse PDF: {err}", file=sys.stderr)
            continue

        sessions = parse_pdf_timetable(pdf_text, race["last_day"])
        entries = build_event_entries(event_name, sessions, track_tz)
        print(f"  [{i}/{len(races)}] {event_name}: {len(entries)} session(s)", file=sys.stderr)
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
