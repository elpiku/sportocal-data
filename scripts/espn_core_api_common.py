#!/usr/bin/env python3
"""
Sport-agnostic ESPN Core API helper.
Shared fetch/retry/parse logic used by multi-sport scrapers.
Uses sports.core.api.espn.com with concurrent batch fetching.
"""

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HEADERS, slugify, make_unique_id_assigner, write_output  # noqa: E402

CORE_API_ROOT = "https://sports.core.api.espn.com/v2/sports"

NAME_SPLIT_PATTERNS = [
    (re.compile(r"^(?P<home>.+?)\s+vs\.?\s+(?P<away>.+)$", re.IGNORECASE)),
    (re.compile(r"^(?P<away>.+?)\s+at\s+(?P<home>.+)$", re.IGNORECASE)),
    (re.compile(r"^(?P<home>.+?)\s+v\s+(?P<away>.+)$", re.IGNORECASE)),
]


def to_utc_iso(date_str: str) -> str | None:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return None


def _get_with_retries(url: str, params: dict | None = None, retries: int = 3, timeout: int = 15):
    """GET with retry/backoff on 429 and transient network errors."""
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            res = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
        except requests.RequestException as err:
            last_error = f"request error: {err}"
            if attempt < retries:
                time.sleep(1.5 ** attempt)
            continue

        if res.status_code == 429:
            last_error = "HTTP 429 (rate limited)"
            if attempt < retries:
                retry_after = res.headers.get("Retry-After")
                sleep_for = float(retry_after) if retry_after else 1.5 ** attempt
                time.sleep(sleep_for)
            continue

        if res.status_code != 200:
            return None, f"HTTP {res.status_code}"

        return res, None

    return None, last_error


def fetch_event_refs(sport: str, league_slug: str, date_from: str, date_to: str) -> tuple[list[str], str | None]:
    """All event $ref URLs for the league in the given date range."""
    url = f"{CORE_API_ROOT}/{sport}/leagues/{league_slug}/events"
    params = {"dates": f"{date_from}-{date_to}", "limit": 1000}

    refs = []
    page = 1
    while True:
        params["page"] = page
        res, error = _get_with_retries(url, params=params)
        if error:
            return refs, error
        try:
            body = res.json()
        except ValueError as err:
            return refs, f"invalid JSON: {err}"

        for item in body.get("items", []):
            ref = item.get("$ref") if isinstance(item, dict) else None
            if ref:
                refs.append(ref)

        page_count = body.get("pageCount", 1)
        if page >= page_count:
            break
        page += 1

    return refs, None


def fetch_event(ref_url: str) -> tuple[dict | None, str | None]:
    """Fetches one event's full object from its $ref URL."""
    res, error = _get_with_retries(ref_url, timeout=12)
    if error:
        return None, error
    try:
        return res.json(), None
    except ValueError as err:
        return None, f"invalid JSON: {err}"


def fetch_league_name(sport: str, league_slug: str) -> str:
    """The league's real display name from ESPN."""
    url = f"{CORE_API_ROOT}/{sport}/leagues/{league_slug}"
    res, error = _get_with_retries(url, params={"lang": "en", "region": "us"}, timeout=15)
    if error:
        return league_slug
    try:
        body = res.json()
    except ValueError:
        return league_slug
    name = body.get("name") or body.get("displayName") or body.get("shortName")
    return name.strip() if isinstance(name, str) and name.strip() else league_slug


def extract_teams(event: dict) -> tuple[str, str] | None:
    """(home_name, away_name) parsed from event name/shortName."""
    for field in ("name", "shortName"):
        raw = event.get(field)
        if not isinstance(raw, str) or not raw.strip():
            continue
        for pattern in NAME_SPLIT_PATTERNS:
            m = pattern.match(raw.strip())
            if m:
                home, away = m.group("home").strip(), m.group("away").strip()
                if home and away:
                    return home, away
    return None


def extract_weekend_label(event: dict, round_prefix: str = "Week") -> str | None:
    """Best-effort round/week label."""
    week = event.get("week")
    if isinstance(week, dict) and week.get("number"):
        return f"{round_prefix} {week['number']}"

    season = event.get("season")
    if isinstance(season, dict):
        for key in ("displayName", "slug", "type"):
            val = season.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

    for note in event.get("notes") or []:
        headline = note.get("headline") if isinstance(note, dict) else None
        if headline:
            return headline.strip()

    return None


def build_events(
    sport: str,
    league_slug: str,
    id_prefix: str,
    sport_key: str,
    date_from: str,
    date_to: str,
    round_prefix: str = "Week",
) -> list[dict]:
    """Fetches and flattens one league's full schedule using concurrent batch requests."""
    print(f"Fetching {sport_key} event list for {date_from}-{date_to}...", file=sys.stderr)
    refs, list_error = fetch_event_refs(sport, league_slug, date_from, date_to)
    if list_error:
        print(f"  ERROR: couldn't fetch event list: {list_error}", file=sys.stderr)
        return []
    print(f"  Found {len(refs)} events, fetching details concurrently...", file=sys.stderr)

    assign_id = make_unique_id_assigner()
    raw_events = []

    # Fetch events in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ref = {executor.submit(fetch_event, ref): ref for ref in refs}
        for future in as_completed(future_to_ref):
            event_obj, error = future.result()
            if event_obj and not error:
                raw_events.append(event_obj)

    events = []
    for event in raw_events:
        utc_iso = to_utc_iso(event.get("date"))
        if not utc_iso:
            continue

        teams = extract_teams(event)
        if teams:
            home, away = teams
            match_name = f"{home} v {away}"
            base_id = f"{id_prefix}-{utc_iso[:10]}-{slugify(home)}-{slugify(away)}"
        else:
            # Fallback for individual/tournament sports (Tennis, Golf, Boxing, MMA, Racing)
            raw_name = event.get("name") or event.get("shortName")
            if not raw_name or not raw_name.strip():
                continue
            match_name = raw_name.strip()
            base_id = f"{id_prefix}-{utc_iso[:10]}-{slugify(match_name)}"

        weekend = extract_weekend_label(event, round_prefix) or utc_iso[:10]

        events.append({
            "id": assign_id(base_id),
            "weekend": weekend,
            "name": match_name,
            "utc": utc_iso,
        })

    events.sort(key=lambda x: x["utc"])
    print(f"Fetched {len(refs)} events -> Kept {len(events)} valid matches/sessions.", file=sys.stderr)
    return events


def run_league_scraper(
    sport: str,
    league_slug: str,
    id_prefix: str,
    sport_key: str,
    season_label: str,
    output_path: Path,
    date_from: str,
    date_to: str,
    round_prefix: str = "Matchweek",
    min_events: int = 20,
):
    events = build_events(sport, league_slug, id_prefix, sport_key, date_from, date_to, round_prefix)
    if len(events) < min_events:
        print(f"WARNING: only {len(events)} events (threshold is {min_events}).", file=sys.stderr)

    league_name = fetch_league_name(sport, league_slug)
    write_output(
        output_path,
        sport_key=sport_key,
        season=season_label,
        events=events,
        league_name=league_name,
    )
