#!/usr/bin/env python3
"""
Country metadata generator and scraper for SportoCal.
Compiles flag emojis, ISO codes, and entity-to-country associations for teams, players, and match venues.

Outputs countries.json at the repo root.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "countries.json"

COUNTRY_FLAGS = {
    "Afghanistan": "🇦🇫", "Albania": "🇦🇱", "Algeria": "🇩🇿", "Argentina": "🇦🇷", "Armenia": "🇦🇲",
    "Australia": "🇦🇺", "Austria": "🇦🇹", "Azerbaijan": "🇦🇿", "Bahrain": "🇧🇭", "Belgium": "🇧🇪",
    "Brazil": "🇧🇷", "Bulgaria": "🇧🇬", "Canada": "🇨🇦", "Chile": "🇨🇱", "China": "🇨🇳",
    "Colombia": "🇨🇴", "Croatia": "🇭🇷", "Czech Republic": "🇨🇿", "Denmark": "🇩🇰", "Egypt": "🇪🇬",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Estonia": "🇪🇪", "Finland": "🇫🇮", "France": "🇫🇷", "Georgia": "🇬🇪",
    "Germany": "🇩🇪", "Great Britain": "🇬🇧", "Greece": "🇬🇷", "Hungary": "🇭🇺", "Iceland": "🇮🇸",
    "India": "🇮🇳", "Indonesia": "🇮🇩", "Ireland": "🇮🇪", "Israel": "🇮🇱", "Italy": "🇮🇹",
    "Japan": "🇯🇵", "Kazakhstan": "🇰🇿", "Kenya": "🇰🇪", "Lithuania": "🇱🇹", "Latvia": "🇱🇻",
    "Mexico": "🇲🇽", "Monaco": "🇲🇨", "Morocco": "🇲🇦", "Netherlands": "🇳🇱", "New Zealand": "🇳🇿",
    "Nigeria": "🇳🇬", "Norway": "🇳🇴", "Paraguay": "🇵🇾", "Peru": "🇵🇪", "Poland": "🇵🇱",
    "Portugal": "🇵🇹", "Qatar": "🇶🇦", "Romania": "🇷🇴", "Russia": "🇷🇺", "Saudi Arabia": "🇸🇦",
    "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Serbia": "🇷🇸", "Singapore": "🇸🇬", "Slovakia": "🇸🇰", "Slovenia": "🇸🇮",
    "South Africa": "🇿🇦", "South Korea": "🇰🇷", "Spain": "🇪🇸", "Sweden": "🇸🇪", "Switzerland": "🇨🇭",
    "Thailand": "🇹🇭", "Turkey": "🇹🇷", "Ukraine": "🇺🇦", "United Arab Emirates": "🇦🇪",
    "United Kingdom": "🇬🇧", "United States": "🇺🇸", "USA": "🇺🇸", "Uruguay": "🇺🇾", "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿"
}

# Grand Prix & Match Venues mapping
VENUE_COUNTRIES = {
    "Monaco": {"country": "Monaco", "flag": "🇲🇨"},
    "Silverstone": {"country": "Great Britain", "flag": "🇬🇧"},
    "Monza": {"country": "Italy", "flag": "🇮🇹"},
    "Spa": {"country": "Belgium", "flag": "🇧🇪"},
    "Suzuka": {"country": "Japan", "flag": "🇯🇵"},
    "Albert Park": {"country": "Australia", "flag": "🇦🇺"},
    "Interlagos": {"country": "Brazil", "flag": "🇧🇷"},
    "Austin": {"country": "United States", "flag": "🇺🇸"},
    "Las Vegas": {"country": "United States", "flag": "🇺🇸"},
    "Miami": {"country": "United States", "flag": "🇺🇸"},
    "Montreal": {"country": "Canada", "flag": "🇨🇦"},
    "Zandvoort": {"country": "Netherlands", "flag": "🇳🇱"},
    "Spielberg": {"country": "Austria", "flag": "🇦🇹"},
    "Hungaroring": {"country": "Hungary", "flag": "🇭🇺"},
    "Bahrain": {"country": "Bahrain", "flag": "🇧🇭"},
    "Jeddah": {"country": "Saudi Arabia", "flag": "🇸🇦"},
    "Abu Dhabi": {"country": "United Arab Emirates", "flag": "🇦🇪"},
    "Qatar": {"country": "Qatar", "flag": "🇶🇦"},
    "Baku": {"country": "Azerbaijan", "flag": "🇦🇿"},
    "Singapore": {"country": "Singapore", "flag": "🇸🇬"},
    "Barcelona": {"country": "Spain", "flag": "🇪🇸"},
    "Madrid": {"country": "Spain", "flag": "🇪🇸"},
    "London": {"country": "England", "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿"},
    "Manchester": {"country": "England", "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿"},
    "Paris": {"country": "France", "flag": "🇫🇷"},
    "Munich": {"country": "Germany", "flag": "🇩🇪"},
    "Milan": {"country": "Italy", "flag": "🇮🇹"},
    "Rome": {"country": "Italy", "flag": "🇮🇹"}
}

def generate_countries():
    print("Compiling country dictionary...")
    data = {
        "flags": COUNTRY_FLAGS,
        "venues": VENUE_COUNTRIES
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Successfully generated {OUTPUT_PATH} with {len(COUNTRY_FLAGS)} countries and {len(VENUE_COUNTRIES)} venues")

if __name__ == "__main__":
    generate_countries()
