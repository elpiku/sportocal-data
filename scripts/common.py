"""
Shared helpers for sportocal-data scrapers.

Every per-sport scraper (scrape_indycar.py, scrape_f1.py, ...) can import
from here to avoid re-implementing the same fetch/id-safety/write logic.
"""

import json
import sys
import re
from pathlib import Path

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def fetch(url: str, timeout: int = 20) -> str:
    """GET a URL with a normal browser User-Agent and raise on HTTP errors."""
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def slugify(text: str) -> str:
    """Lowercase, hyphenate, strip anything that isn't alphanumeric."""
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def make_unique_id_assigner():
    """
    Returns a function `assign(base_id) -> unique_id` that guarantees no two
    calls return the same string, appending `-2`, `-3`, ... on collision.
    Use a fresh assigner per weekend/event group (don't share across the
    whole season) so ids stay predictable.
    """
    used = set()

    def assign(base_id: str) -> str:
        candidate = base_id
        n = 1
        while candidate in used:
            n += 1
            candidate = f"{base_id}-{n}"
        used.add(candidate)
        return candidate

    return assign


def write_output(output_path: Path, data: dict, min_events: int = 1):
    """
    Write `data` (must contain an "events" list) to `output_path` as JSON.
    Aborts (raises SystemExit) without writing if fewer than `min_events`
    events were found -- this is the safety net that stops a broken scrape
    (e.g. after a site redesign) from overwriting good data with garbage.
    """
    event_count = len(data.get("events", []))
    if event_count < min_events:
        print(
            f"ERROR: only parsed {event_count} events (minimum {min_events}). "
            f"Site structure may have changed. Aborting without writing output.",
            file=sys.stderr,
        )
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Wrote {event_count} events to {output_path}", file=sys.stderr)
