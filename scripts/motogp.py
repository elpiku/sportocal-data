#!/usr/bin/env python3
"""
MotoGP / Moto2 / Moto3 schedule scraper for the sportocal-data repo.

Fetches full weekend sessions (FP1, Practice, Q1, Q2, Sprint, Warm Up,
Race) via MotoGP's official (undocumented) PulseLive REST API and writes:
- motorsport/motorcycleracing/motogp/2026.json
- motorsport/motorcycleracing/moto2/2026.json
- motorsport/motorcycleracing/moto3/2026.json

This replaces a previous version of the script that always fell back to a
single "race"-only placeholder for every event, for two compounding
reasons (both fixed here):

  1. It called `/results/events/{id}/schedule`, which isn't a real
     endpoint on this API - it either 404s or 200s with a shape this
     script didn't expect, so the per-session data was never read. The
     real endpoint for a weekend's sessions is
     `/results/sessions?eventUuid={event}&categoryUuid={category}`
     (see https://github.com/robschmitt/MotoGP-API for the closest thing
     to official docs of this hidden API).
  2. Category names returned by the API include a trademark symbol
     ("MotoGP™", "Moto2™", "Moto3™"). The old code lowercased the name
     and looked it up in a plain-text dict ("motogp", "moto2", "moto3"),
     which can never match because of the "™" - so even a working
     sessions call would have been silently discarded. This version
     resolves category UUIDs once up front instead of matching on name
     per-session.

Run this from the repo root: python scripts/motogp.py
"""

import sys
from datetime import timezone
from pathlib import Path

import requests
from dateutil import parser as dt_parser

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HEADERS, slugify, make_unique_id_assigner, write_output  # noqa: E402

SEASON_YEAR = 2026  # bump each year
BASE_API = "https://api.motogp.pulselive.com/motogp/v1"

OUTPUT_PATHS = {
    "motogp": Path(__file__).resolve().parent.parent / "motorsport/motorcycleracing/motogp" / f"{SEASON_YEAR}.json",
    "moto2": Path(__file__).resolve().parent.parent / "motorsport/motorcycleracing/moto2" / f"{SEASON_YEAR}.json",
    "moto3": Path(__file__).resolve().parent.parent / "motorsport/motorcycleracing/moto3" / f"{SEASON_YEAR}.json",
}

# The API's category names carry a trademark symbol ("MotoGP™") and don't
# include MotoE, which this repo doesn't track - strip the symbol and
# match against this plain-text set instead of relying on exact equality.
TARGET_CATEGORIES = {"motogp", "moto2", "moto3"}

# Session "type" codes returned by /results/sessions -> (id slug, display
# name). MotoGP's own class uses FP1/FP2/Q1/Q2/SPR/WUP/RAC; Moto2/Moto3
# use PR1/PR2 instead of FP1/FP2 for practice (see
# https://en.wikipedia.org/wiki/2024_Qatar_motorcycle_Grand_Prix for the
# naming difference between classes). Matched case-insensitively.
SESSION_TYPE_MAP = {
    "FP1": ("fp1", "Free Practice 1"),
    "FP2": ("fp2", "Free Practice 2"),
    "FP3": ("fp3", "Free Practice 3"),
    "FP4": ("fp4", "Free Practice 4"),
    "PR1": ("practice_1", "Practice 1"),
    "PR2": ("practice_2", "Practice 2"),
    "PR": ("practice", "Practice"),
    "P1": ("practice_1", "Practice 1"),
    "P2": ("practice_2", "Practice 2"),
    "P": ("practice", "Practice"),
    "Q1": ("qualifying_1", "Qualifying 1"),
    "Q2": ("qualifying_2", "Qualifying 2"),
    "Q": ("qualifying", "Qualifying"),
    "SPR": ("sprint", "Sprint"),
    "SP": ("sprint", "Sprint"),
    "WUP": ("warmup", "Warm Up"),
    "RAC": ("race", "Race"),
    "RACE": ("race", "Race"),
}


def api_get(path: str, **params) -> list | dict:
    res = requests.get(f"{BASE_API}{path}", headers=HEADERS, params=params, timeout=15)
    res.raise_for_status()
    return res.json()


def to_utc_iso(date_str: str) -> str | None:
    if not date_str:
        return None
    try:
        dt = dt_parser.parse(str(date_str))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OverflowError):
        return None


def classify_session(type_code: str, session_num=None) -> tuple[str, str]:
    raw = (type_code or "").upper().strip()
    if session_num is not None and str(session_num).isdigit():
        combined = f"{raw}{session_num}"
        mapped = SESSION_TYPE_MAP.get(combined)
        if mapped:
            return mapped
    mapped = SESSION_TYPE_MAP.get(raw)
    if mapped:
        return mapped
    fallback_slug = slugify(f"{raw}-{session_num}" if session_num else raw or "session")
    return fallback_slug, (f"{raw} {session_num}".strip() if session_num else raw or "Session")


def get_season_uuid(year: int) -> str:
    seasons = api_get("/results/seasons")
    for s in seasons:
        if s.get("year") == year:
            return s.get("id")
    # Fall back to whichever season the API currently marks "current"
    for s in seasons:
        if s.get("current"):
            print(f"WARNING: season {year} not found, using current season instead", file=sys.stderr)
            return s.get("id")
    raise RuntimeError(f"No season found for year {year} and no current season either")


def get_target_category_ids(season_uuid: str) -> dict[str, str]:
    """{"motogp": uuid, "moto2": uuid, "moto3": uuid} - strips the "™"
    the API attaches to category names before matching."""
    categories = api_get("/results/categories", seasonUuid=season_uuid)
    ids = {}
    for cat in categories:
        name = (cat.get("name") or "").replace("™", "").strip().lower()
        if name in TARGET_CATEGORIES:
            ids[name] = cat.get("id")
    missing = TARGET_CATEGORIES - ids.keys()
    if missing:
        print(f"WARNING: couldn't find category id(s) for: {missing}", file=sys.stderr)
    return ids


def get_events(season_uuid: str) -> list[dict]:
    events = api_get("/results/events", seasonUuid=season_uuid)
    return [ev for ev in events if not ev.get("test")]  # exclude pre-season tests


def fetch_event_sessions(event_uuid: str, category_uuid: str) -> list[dict]:
    try:
        return api_get("/results/sessions", eventUuid=event_uuid, categoryUuid=category_uuid)
    except requests.RequestException as err:
        print(f"  Failed to fetch sessions for event={event_uuid} category={category_uuid}: {err}", file=sys.stderr)
        return []


def build_event_entries(event: dict, category_ids: dict[str, str]) -> dict[str, list[dict]]:
    """Returns {"motogp": [...], "moto2": [...], "moto3": [...]} of flat
    schema events for one Grand Prix weekend."""
    event_name = event.get("name") or event.get("sponsored_name") or "Grand Prix"
    event_slug = slugify(event_name)
    fallback_date = event.get("date_start") or event.get("date_end")

    entries = {cat: [] for cat in TARGET_CATEGORIES}
    for cat, category_uuid in category_ids.items():
        assign_id = make_unique_id_assigner()
        sessions = fetch_event_sessions(event.get("id"), category_uuid)

        if not sessions:
            # No session data available yet for this weekend/category -
            # fall back to a single race placeholder rather than dropping
            # the event entirely.
            utc_iso = to_utc_iso(fallback_date)
            if utc_iso:
                entries[cat].append({
                    "id": assign_id(f"{cat}-{SEASON_YEAR}-{event_slug}-race"),
                    "weekend": event_name,
                    "name": "Race",
                    "utc": utc_iso,
                })
            continue

        for s in sessions:
            utc_iso = to_utc_iso(s.get("date"))
            if not utc_iso:
                continue
            session_key, display_name = classify_session(s.get("type"), s.get("number"))
            entries[cat].append({
                "id": assign_id(f"{cat}-{SEASON_YEAR}-{event_slug}-{session_key}"),
                "weekend": event_name,
                "name": display_name,
                "utc": utc_iso,
            })

    return entries


def main():
    print(f"Resolving season UUID for {SEASON_YEAR}...", file=sys.stderr)
    season_uuid = get_season_uuid(SEASON_YEAR)

    print("Resolving category UUIDs (MotoGP/Moto2/Moto3)...", file=sys.stderr)
    category_ids = get_target_category_ids(season_uuid)
    if not category_ids:
        print("ERROR: no target categories resolved, aborting", file=sys.stderr)
        sys.exit(1)

    print("Fetching event list...", file=sys.stderr)
    events = get_events(season_uuid)
    print(f"Got {len(events)} non-test events", file=sys.stderr)

    all_events = {"motogp": [], "moto2": [], "moto3": []}
    for i, event in enumerate(events, 1):
        entries = build_event_entries(event, category_ids)
        for cat in all_events:
            all_events[cat].extend(entries[cat])
        print(f"  [{i}/{len(events)}] {event.get('name')}", file=sys.stderr)

    for cat, output_path in OUTPUT_PATHS.items():
        events_for_cat = sorted(all_events[cat], key=lambda e: e["utc"])
        output = {
            "sportKey": cat,
            "season": str(SEASON_YEAR),
            "events": events_for_cat,
        }
        write_output(output_path, output, min_events=5)


if __name__ == "__main__":
    main()
