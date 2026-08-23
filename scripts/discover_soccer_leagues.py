#!/usr/bin/env python3
"""
Discovers every soccer competition slug ESPN's Core API currently lists,
so the "scrape everything" workflow doesn't need a hand-maintained list.

GET sports.core.api.espn.com/v2/sports/soccer/leagues?limit=1000
returns a paginated collection of {"$ref": ".../leagues/{slug}?..."}
stubs - one per competition. The slug is embedded in the $ref URL
itself, so this needs zero follow-up calls per league; it's one cheap,
paginated request regardless of how many hundred competitions ESPN has.

Usage:
  python scripts/discover_soccer_leagues.py                 # prints one slug per line
  python scripts/discover_soccer_leagues.py --batch-size 15  # prints JSON: list of slug-batches
  python scripts/discover_soccer_leagues.py --github-output batches  # also writes
      `batches=<json>` to $GITHUB_OUTPUT for a workflow matrix step
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HEADERS  # noqa: E402
import requests

LEAGUES_URL = "https://sports.core.api.espn.com/v2/sports/soccer/leagues"
REF_SLUG_RE = re.compile(r"/leagues/([^/?]+)")


def discover_slugs() -> list[str]:
    slugs = []
    page = 1
    while True:
        res = requests.get(
            LEAGUES_URL, headers=HEADERS, params={"limit": 1000, "page": page}, timeout=20
        )
        res.raise_for_status()
        body = res.json()

        for item in body.get("items", []):
            ref = item.get("$ref") if isinstance(item, dict) else None
            if not ref:
                continue
            m = REF_SLUG_RE.search(ref)
            if m:
                slugs.append(m.group(1))

        page_count = body.get("pageCount", 1)
        if page >= page_count:
            break
        page += 1

    # Stable order, de-duplicated (a slug could theoretically repeat across pages
    # if ESPN's collection shifts under us mid-pagination).
    seen = set()
    unique = []
    for s in slugs:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=None,
                         help="If set, output JSON batches of this many slugs each instead of one-per-line.")
    parser.add_argument("--github-output", metavar="VAR_NAME", default=None,
                         help="Also write '<VAR_NAME>=<json>' to $GITHUB_OUTPUT (requires --batch-size).")
    args = parser.parse_args()

    slugs = discover_slugs()
    print(f"Discovered {len(slugs)} soccer competition slugs.", file=sys.stderr)

    if args.batch_size:
        batches = chunk(slugs, args.batch_size)
        payload = json.dumps(batches)
        print(payload)
        if args.github_output:
            gh_out = os.environ.get("GITHUB_OUTPUT")
            if not gh_out:
                print("  WARNING: --github-output given but $GITHUB_OUTPUT is not set; skipping.", file=sys.stderr)
            else:
                with open(gh_out, "a") as f:
                    f.write(f"{args.github_output}={payload}\n")
    else:
        for s in slugs:
            print(s)


if __name__ == "__main__":
    main()
