#!/usr/bin/env python3
"""
Builds a single index.json listing every available league/competition
file in the repo.

Indexed files carry sportKey + events fields and may have a leagueName.
CURATED_NAMES maps sportKey -> display name for those that don't.

Run from repo root: python scripts/build_index.py
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "index.json"
BASE_URL = "https://elpiku.github.io/sportocal-data"

EXCLUDED_TOP_LEVEL = {".git", ".github", "scripts", "node_modules"}

# Folders that contain licensed API data
LICENSED_FOLDERS = {"api-sports", "football-data", "balldontlie"}

# Display names for curated (fixed-path) files keyed by sportKey.
# Only needed when the JSON file itself doesn't carry a "leagueName" field.
CURATED_NAMES = {
    # Motorsport
    "f1": "Formula 1",
    "f2": "Formula 2",
    "f3": "Formula 3",
    "gt-world-challenge-europe": "GT World Challenge Europe",
    "gb3": "GB3 Championship",
    "gb4": "GB4 Championship",
    "freca": "Formula Regional European Championship",
    "italian-f4": "Italian F4 Championship",
    "tcr-europe": "TCR Europe",
    "imsa": "IMSA WeatherTech SportsCar Championship",
    "super-formula": "Super Formula",
    "wrc": "WRC",
    "nascar-cup": "NASCAR Cup Series",
    "nascar-oreilly": "NASCAR O'Reilly Series",
    "nascar-craftsman": "NASCAR Craftsman Trucks",
    "ntt-indycar": "IndyCar NTT",
    "motogp": "MotoGP",
    "moto2": "Moto2",
    "moto3": "Moto3",
    "wec": "World Endurance Championship",
    # Football (from football-data.org curated scripts)
    "premierleague": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "bundesliga": "Bundesliga",
    "uefachampionsleague": "UEFA Champions League",
    "uefaeuropaleague": "UEFA Europa League",
    "uefaconferenceleague": "UEFA Conference League",
    "championsleague": "UEFA Champions League",
    "ligue1": "Ligue 1",
    "eredivisie": "Eredivisie",
    "primeiraliga": "Primeira Liga",
    "championship": "EFL Championship",
    "mls": "MLS",
    # Basketball (curated)
    "nba": "NBA",
    # Tennis (curated)
    "atp": "ATP Tour",
    "wta": "WTA Tour",
    # Hockey (curated)
    "nhl": "NHL",
}


def year_from_filename(path: Path) -> int:
    m = re.match(r"^(\d{4})\.json$", path.name)
    return int(m.group(1)) if m else -1


def find_all_json_files() -> list[Path]:
    return [
        p for p in REPO_ROOT.rglob("*.json")
        if p.name != "index.json"
        and EXCLUDED_TOP_LEVEL.isdisjoint(p.relative_to(REPO_ROOT).parts)
    ]


def build_index() -> list[dict]:
    files = find_all_json_files()

    # Separate by provider folder type
    licensed_files: list[Path] = []   # api-sports/, football-data/, balldontlie/
    curated_by_folder: dict[Path, list[Path]] = {}  # everything else

    for f in files:
        rel = f.relative_to(REPO_ROOT)
        parts = set(rel.parts)
        if parts & LICENSED_FOLDERS:
            licensed_files.append(f)
        else:
            curated_by_folder.setdefault(f.parent, []).append(f)

    entries = []
    skipped_no_name = 0

    # ── Curated files (one winner per folder = highest year filename) ────────
    for folder, candidates in curated_by_folder.items():
        candidates.sort(key=year_from_filename)
        chosen = candidates[-1]
        try:
            data = json.loads(chosen.read_text())
        except (json.JSONDecodeError, OSError) as err:
            print(f"  WARNING: couldn't read {chosen}: {err}", file=sys.stderr)
            continue

        if "sportKey" not in data or "events" not in data:
            continue  # non-schedule file (e.g. championship.json) — skip

        sport_key = data["sportKey"]
        name = data.get("leagueName") or CURATED_NAMES.get(sport_key)
        if not name:
            skipped_no_name += 1
            print(
                f"  WARNING: no display name for sportKey '{sport_key}' "
                f"({chosen.relative_to(REPO_ROOT)}) — add to CURATED_NAMES.",
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

    # ── Licensed API files (api-sports/, football-data/, etc.) ──────────────
    for f in licensed_files:
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError) as err:
            print(f"  WARNING: couldn't read {f}: {err}", file=sys.stderr)
            continue

        if "sportKey" not in data or "events" not in data:
            continue

        rel = f.relative_to(REPO_ROOT)
        provider_folder = next(
            (p for p in rel.parts if p in LICENSED_FOLDERS), "licensed"
        )
        entries.append({
            "name": data.get("leagueName") or CURATED_NAMES.get(data["sportKey"], data["sportKey"]),
            "sportKey": data["sportKey"],
            "category": rel.parts[0],
            "season": data.get("season"),
            "windowFrom": data.get("windowFrom"),
            "windowTo": data.get("windowTo"),
            "eventCount": len(data["events"]),
            "provider": provider_folder,
            "url": f"{BASE_URL}/{rel.as_posix()}",
        })

    entries.sort(key=lambda e: (e["category"], e["name"]))

    if skipped_no_name:
        print(
            f"\n{skipped_no_name} curated file(s) had no display name — see warnings above.",
            file=sys.stderr,
        )

    return entries


def main():
    entries = build_index()
    output = {
        "generatedAt": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(entries),
        "leagues": entries,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2) + "\n")
    print(f"Wrote {len(entries)} league(s) to {OUTPUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
