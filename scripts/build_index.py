#!/usr/bin/env python3
"""
Builds a single index.json at the repo root listing every available
league/competition file in the repo - so a consuming app (or anything
else) can fetch ONE file and get the full, always-current list instead
of hardcoding every path.

Two kinds of files get indexed, handled differently:

  - "espn-all" bulk-discovered files (basketball/espn-all/wnba.json etc.)
    already carry a "leagueName" field written by basketball_generic.py /
    soccer_generic.py - fully self-describing, no manual work needed here
    ever, even as new leagues get discovered or drop off.

  - Curated files (motorsport/f1/2026.json etc.) don't carry a display
    name in their own JSON, just a bare "sportKey" - CURATED_NAMES below
    is the one place that needs a new line whenever a brand-new curated
    scraper is added. That's the only manual step left anywhere in this
    pipeline; the Android app itself never needs touching again.

Stale duplicate seasons (e.g. basketball/nba/2026.json AND .../2027.json
both existing because a scraper's very first successful run landed in a
different file than an old manually-seeded placeholder) are resolved by
keeping only the file with the highest year in its filename per folder.

Non-schedule files (motorsport/wrc/championship.json, .../schedule.json -
standings/calendar data, not the {sportKey, events} shape) are skipped
since they don't fit this index's format.

Run this from the repo root: python scripts/build_index.py
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "index.json"
BASE_URL = "https://elpiku.github.io/sportocal-data"

EXCLUDED_TOP_LEVEL = {".git", ".github", "scripts", "node_modules"}

# The one place a human needs to add a line when a new *curated* (fixed-
# path, non-"espn-all") scraper is introduced. Keyed by the "sportKey"
# each script's own output already contains.
CURATED_NAMES = {
    "f1": "Formula 1",
    "wrc": "WRC",
    "nascar-cup": "NASCAR Cup Series",
    "nascar-oreilly": "NASCAR O'Reilly Series",
    "nascar-craftsman": "NASCAR Craftsman Trucks",
    "ntt-indycar": "IndyCar NTT",
    "motogp": "MotoGP",
    "moto2": "Moto2",
    "moto3": "Moto3",
    "wec": "World Endurance Championship",
    "premierleague": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "bundesliga": "Bundesliga",
    "uefachampionsleague": "UEFA Champions League",
    "championsleague": "UEFA Champions League",
    "mls": "MLS",
    "nba": "NBA",
    "atp": "ATP Tour",
    "wta": "WTA Tour",
    "nhl": "NHL",
}


def year_from_filename(path: Path) -> int:
    m = re.match(r"^(\d{4})\.json$", path.name)
    return int(m.group(1)) if m else -1


def find_all_json_files() -> list[Path]:
    return [
        p for p in REPO_ROOT.rglob("*.json")
        if p.name != "index.json" and EXCLUDED_TOP_LEVEL.isdisjoint(p.relative_to(REPO_ROOT).parts)
    ]


def build_index() -> list[dict]:
    files = find_all_json_files()

    # Group curated (non-espn-all) files by their parent folder so stale
    # duplicate seasons in the same folder can be resolved to just the
    # newest one before building final entries.
    by_folder: dict[Path, list[Path]] = {}
    espn_all_files: list[Path] = []

    for f in files:
        rel = f.relative_to(REPO_ROOT)
        if "espn-all" in rel.parts:
            espn_all_files.append(f)
        else:
            by_folder.setdefault(f.parent, []).append(f)

    entries = []
    skipped_no_name = 0

    # Curated files: one winner per folder (highest season-year filename)
    for folder, candidates in by_folder.items():
        candidates.sort(key=year_from_filename)
        chosen = candidates[-1]
        try:
            data = json.loads(chosen.read_text())
        except (json.JSONDecodeError, OSError) as err:
            print(f"  WARNING: couldn't read {chosen}: {err}", file=sys.stderr)
            continue

        if "sportKey" not in data or "events" not in data:
            continue  # not a schedule file (e.g. wrc/championship.json) - skip

        sport_key = data["sportKey"]
        name = CURATED_NAMES.get(sport_key)
        if not name:
            skipped_no_name += 1
            print(
                f"  WARNING: no display name for sportKey '{sport_key}' ({chosen.relative_to(REPO_ROOT)}) - "
                f"add it to CURATED_NAMES in this script. Using the raw sportKey for now.",
                file=sys.stderr,
            )
            name = sport_key

        rel = chosen.relative_to(REPO_ROOT)
        entries.append({
            "name": name,
            "sportKey": sport_key,
            "category": rel.parts[0],
            "season": data.get("season"),
            "eventCount": len(data["events"]),
            "url": f"{BASE_URL}/{rel.as_posix()}",
        })

    # espn-all files: self-describing via "leagueName", no dedup needed
    # (each slug only ever has one file, no season-year in the filename)
    for f in espn_all_files:
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError) as err:
            print(f"  WARNING: couldn't read {f}: {err}", file=sys.stderr)
            continue

        if "sportKey" not in data or "events" not in data:
            continue

        rel = f.relative_to(REPO_ROOT)
        entries.append({
            "name": data.get("leagueName") or data["sportKey"],
            "sportKey": data["sportKey"],
            "category": rel.parts[0],
            "season": None,  # espn-all uses a rolling window, not a fixed season
            "windowFrom": data.get("windowFrom"),
            "windowTo": data.get("windowTo"),
            "eventCount": len(data["events"]),
            "url": f"{BASE_URL}/{rel.as_posix()}",
        })

    entries.sort(key=lambda e: (e["category"], e["name"]))

    if skipped_no_name:
        print(f"\n{skipped_no_name} curated file(s) had no display name mapped - see warnings above.", file=sys.stderr)

    return entries


def main():
    entries = build_index()
    output = {
        "generatedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(entries),
        "leagues": entries,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2) + "\n")
    print(f"Wrote {len(entries)} league(s) to {OUTPUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
