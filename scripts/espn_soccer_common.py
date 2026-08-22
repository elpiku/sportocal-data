#!/usr/bin/env python3
"""
Shared helper for the football/soccer scrapers in this repo (Premier
League, Champions League, La Liga, Serie A, Bundesliga, MLS).

Uses ESPN's public "Core API", the same family of endpoint already used
successfully elsewhere in this repo (scripts/motogp.py's season/category/
event-list pattern) - it's well documented as being structurally
consistent across every sport ESPN covers, not just soccer, which is why
the same list -> "$ref" per item -> fetch full event approach is reused
here:

  1. GET .../leagues/{league}/events?dates=START-END&limit=1000
     Returns a paged list of lightweight {"$ref": "..."} stubs for every
     match in the date range - NOT full match data.
  2. GET each event's own "$ref" URL for the actual match: kickoff time,
     home/away teams, and (where available) the matchweek/round label.

IMPORTANT CAVEAT: this was built from documentation and community
references (ESPN doesn't publish an official spec), not from a live test
against espn.com - the sandbox this was written in has no network access
to ESPN's domains. The list -> $ref -> event-detail shape is the same
one already confirmed working for this repo's NASCAR/MotoGP scrapers, so
there's good reason to expect it holds for soccer too, but if a league's
first real run comes back with 0 events or missing matchweek labels, that
mismatch between documented and actual behavior is the first thing to
check - the field-extraction in build_events() below is where to adjust.

Run any of the per-league scripts from the repo root, e.g.:
  python scripts/premier_league.py
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HEADERS, slugify, make_unique_id_assigner, write_output  # noqa: E402

CORE_API_BASE = "https://sports.core.api.espn.com/v2/sports/soccer/leagues"


def to_utc_iso(date_str: str) -> str | None:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def fetch_event_refs(league_slug: str, date_from: str, date_to: str) -> list[str]:
    """date_from/date_to are 'YYYYMMDD' strings. Returns every event's
    "$ref" URL in the range - each still needs its own fetch for full
    match details (see fetch_event)."""
    url = f"{CORE_API_BASE}/{league_slug}/events"
    params = {"dates": f"{date_from}-{date_to}", "limit": 1000}
    res = requests.get(url, headers=HEADERS, params=params, timeout=20)
    res.raise_for_status()
    items = res.json().get("items", [])
    return [item["$ref"] for item in items if isinstance(item, dict) and item.get("$ref")]


def fetch_event(ref_url: str) -> dict | None:
    try:
        res = requests.get(ref_url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            return None
        return res.json()
    except requests.RequestException:
        return None


def extract_teams(event: dict) -> tuple[str, str] | None:
    """(home_name, away_name) from an ESPN event's competitors list."""
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    competitors = competitions[0].get("competitors") or []

    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if not home or not away:
        return None

    def team_name(c: dict) -> str | None:
        team = c.get("team")
        if isinstance(team, dict):
            return team.get("displayName") or team.get("name")
        return None

    home_name, away_name = team_name(home), team_name(away)
    if not home_name or not away_name:
        return None
    return home_name, away_name


def extract_weekend_label(event: dict, round_prefix: str = "Matchweek") -> str | None:
    """Best-effort matchweek/round label - ESPN's soccer events sometimes
    carry a numbered week, sometimes a named round (e.g. Champions League
    group/knockout stage) depending on the competition. Tries a few
    plausible field locations; returns None if nothing usable is found
    (caller should fall back to something date-based rather than guess)."""
    week = event.get("week")
    if isinstance(week, dict) and week.get("number"):
        return f"{round_prefix} {week['number']}"

    season = event.get("season")
    if isinstance(season, dict):
        for key in ("displayName", "slug", "type"):
            val = season.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

    competitions = event.get("competitions") or []
    for comp in competitions:
        for note in comp.get("notes") or []:
            headline = note.get("headline")
            if headline:
                return headline.strip()

    return None


def build_events(
    league_slug: str,
    id_prefix: str,
    sport_key: str,
    date_from: str,
    date_to: str,
    round_prefix: str = "Matchweek",
) -> list[dict]:
    """Fetches and flattens one league's full schedule for the given date
    range into this repo's standard {id, weekend, name, utc} shape."""
    print(f"Fetching {sport_key} event list ({date_from} to {date_to})...", file=sys.stderr)
    refs = fetch_event_refs(league_slug, date_from, date_to)
    print(f"Found {len(refs)} events, fetching details...", file=sys.stderr)

    assign_id = make_unique_id_assigner()
    events = []
    for i, ref in enumerate(refs, 1):
        event = fetch_event(ref)
        if not event:
            continue

        utc_iso = to_utc_iso(event.get("date"))
        teams = extract_teams(event)
        if not utc_iso or not teams:
            continue
        home, away = teams

        weekend = extract_weekend_label(event, round_prefix) or utc_iso[:10]
        match_name = f"{home} v {away}"
        base_id = f"{id_prefix}-{utc_iso[:10]}-{slugify(home)}-{slugify(away)}"

        events.append({
            "id": assign_id(base_id),
            "weekend": weekend,
            "name": match_name,
            "utc": utc_iso,
        })

        if i % 50 == 0:
            print(f"  ...{i}/{len(refs)}", file=sys.stderr)

    events.sort(key=lambda e: e["utc"])
    return events


def run_league_scraper(
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
    """Shared entrypoint for each per-league script's main()."""
    events = build_events(league_slug, id_prefix, sport_key, date_from, date_to, round_prefix)
    output = {
        "sportKey": sport_key,
        "season": season_label,
        "events": events,
    }
    write_output(output_path, output, min_events=min_events)
