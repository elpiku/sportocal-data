#!/usr/bin/env python3
"""
Scrapes and compiles complete athlete, driver, and player rosters strictly
for the sports leagues and competitions tracked by SportoCal.
Fetches official squad rosters from ESPN Core API and motorsport driver grids.
Generates players.json at the repo root.

Run: python scripts/scrape_players.py
"""

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "players.json"

COUNTRY_FLAGS = {
    "Afghanistan": "🇦🇫", "Albania": "🇦🇱", "Algeria": "🇩🇿", "Argentina": "🇦🇷", "Armenia": "🇦🇲",
    "Australia": "🇦🇺", "Austria": "🇦🇹", "Azerbaijan": "🇦🇿", "Bahrain": "🇧🇭", "Belgium": "🇧🇪",
    "Brazil": "🇧🇷", "Bulgaria": "🇧🇬", "Canada": "🇨🇦", "Chile": "🇨🇱", "China": "🇨🇳",
    "Colombia": "🇨🇴", "Croatia": "🇭🇷", "Czech Republic": "🇨🇿", "Denmark": "🇩🇰", "Egypt": "🇪🇬",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Estonia": "🇪🇪", "Finland": "🇫🇮", "France": "🇫🇷", "Georgia": "🇬🇪",
    "Germany": "🇩🇪", "Ghana": "🇬🇭", "Great Britain": "🇬🇧", "Greece": "🇬🇷", "Hungary": "🇭🇺",
    "Iceland": "🇮🇸", "India": "🇮🇳", "Indonesia": "🇮🇩", "Ireland": "🇮🇪", "Israel": "🇮🇱",
    "Italy": "🇮🇹", "Ivory Coast": "🇨🇮", "Cote d'Ivoire": "🇨🇮", "Jamaica": "🇯🇲", "Japan": "🇯🇵",
    "Kazakhstan": "🇰🇿", "Kenya": "🇰🇪", "Lithuania": "🇱🇹", "Latvia": "🇱🇻", "Mali": "🇲🇱",
    "Mexico": "🇲🇽", "Monaco": "🇲🇨", "Montenegro": "🇲🇪", "Morocco": "🇲🇦", "Netherlands": "🇳🇱",
    "New Zealand": "🇳🇿", "Nigeria": "🇳🇬", "Northern Ireland": "🇬🇧", "Norway": "🇳🇴",
    "Paraguay": "🇵🇾", "Peru": "🇵🇪", "Poland": "🇵🇱", "Portugal": "🇵🇹", "Qatar": "🇶🇦",
    "Romania": "🇷🇴", "Russia": "🇷🇺", "Saudi Arabia": "🇸🇦", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Senegal": "🇸🇳", "Serbia": "🇷🇸", "Singapore": "🇸🇬", "Slovakia": "🇸🇰", "Slovenia": "🇸🇮",
    "South Africa": "🇿🇦", "South Korea": "🇰🇷", "Spain": "🇪🇸", "Sweden": "🇸🇪", "Switzerland": "🇨🇭",
    "Thailand": "🇹🇭", "Turkey": "🇹🇷", "Ukraine": "🇺🇦", "United Arab Emirates": "🇦🇪",
    "United Kingdom": "🇬🇧", "United States": "🇺🇸", "USA": "🇺🇸", "Uruguay": "🇺🇾",
    "Venezuela": "🇻🇪", "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿"
}

def format_country(country_raw: str) -> str:
    if not country_raw:
        return "🌍 Global"
    country_clean = country_raw.strip()
    flag = COUNTRY_FLAGS.get(country_clean)
    if not flag:
        for c_name, c_flag in COUNTRY_FLAGS.items():
            if c_name.lower() == country_clean.lower():
                flag = c_flag
                break
    return f"{flag} {country_clean}" if flag else country_clean

def fetch_json(url: str):
    """Fetches JSON via requests if available, falling back to curl or urllib."""
    try:
        import requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*'
        }
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    try:
        import subprocess
        cmd = ['curl.exe', '-s', url] if sys.platform == 'win32' else ['curl', '-s', url]
        out = subprocess.check_output(cmd, timeout=12)
        return json.loads(out.decode('utf-8'))
    except Exception:
        pass

    return None

# 1. Motorsport Drivers (Grid Rosters for the App's Racing Series)
MOTORSPORT_ATHLETES = [
    # Formula 1
    {"name": "Max Verstappen", "team": "Red Bull Racing", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇳🇱 Netherlands", "category": "MOTORSPORT"},
    {"name": "Lewis Hamilton", "team": "Ferrari", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇬🇧 Great Britain", "category": "MOTORSPORT"},
    {"name": "Charles Leclerc", "team": "Ferrari", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇲🇨 Monaco", "category": "MOTORSPORT"},
    {"name": "Lando Norris", "team": "McLaren", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇬🇧 Great Britain", "category": "MOTORSPORT"},
    {"name": "Oscar Piastri", "team": "McLaren", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇦🇺 Australia", "category": "MOTORSPORT"},
    {"name": "George Russell", "team": "Mercedes", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇬🇧 Great Britain", "category": "MOTORSPORT"},
    {"name": "Fernando Alonso", "team": "Aston Martin", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇪🇸 Spain", "category": "MOTORSPORT"},
    {"name": "Carlos Sainz", "team": "Williams", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇪🇸 Spain", "category": "MOTORSPORT"},
    {"name": "Liam Lawson", "team": "Red Bull Racing", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇳🇿 New Zealand", "category": "MOTORSPORT"},
    {"name": "Alex Albon", "team": "Williams", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇹🇭 Thailand", "category": "MOTORSPORT"},
    {"name": "Yuki Tsunoda", "team": "RB", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇯🇵 Japan", "category": "MOTORSPORT"},
    {"name": "Isack Hadjar", "team": "RB", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇫🇷 France", "category": "MOTORSPORT"},
    {"name": "Pierre Gasly", "team": "Alpine", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇫🇷 France", "category": "MOTORSPORT"},
    {"name": "Jack Doohan", "team": "Alpine", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇦🇺 Australia", "category": "MOTORSPORT"},
    {"name": "Nico Hülkenberg", "team": "Sauber", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇩🇪 Germany", "category": "MOTORSPORT"},
    {"name": "Gabriel Bortoleto", "team": "Sauber", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇧🇷 Brazil", "category": "MOTORSPORT"},
    {"name": "Esteban Ocon", "team": "Haas", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇫🇷 France", "category": "MOTORSPORT"},
    {"name": "Oliver Bearman", "team": "Haas", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇬🇧 Great Britain", "category": "MOTORSPORT"},
    {"name": "Lance Stroll", "team": "Aston Martin", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇨🇦 Canada", "category": "MOTORSPORT"},
    {"name": "Kimi Antonelli", "team": "Mercedes", "leagueId": "f1", "leagueName": "Formula 1", "country": "🇮🇹 Italy", "category": "MOTORSPORT"},

    # MotoGP
    {"name": "Marc Márquez", "team": "Ducati Lenovo", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇪🇸 Spain", "category": "MOTORSPORT"},
    {"name": "Francesco Bagnaia", "team": "Ducati Lenovo", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇮🇹 Italy", "category": "MOTORSPORT"},
    {"name": "Jorge Martín", "team": "Aprilia Racing", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇪🇸 Spain", "category": "MOTORSPORT"},
    {"name": "Pedro Acosta", "team": "Red Bull KTM", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇪🇸 Spain", "category": "MOTORSPORT"},
    {"name": "Brad Binder", "team": "Red Bull KTM", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇿🇦 South Africa", "category": "MOTORSPORT"},
    {"name": "Marco Bezzecchi", "team": "Aprilia Racing", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇮🇹 Italy", "category": "MOTORSPORT"},
    {"name": "Fabio Quartararo", "team": "Monster Yamaha", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇫🇷 France", "category": "MOTORSPORT"},
    {"name": "Maverick Viñales", "team": "Tech3 KTM", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇪🇸 Spain", "category": "MOTORSPORT"},
    {"name": "Enea Bastianini", "team": "Tech3 KTM", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇮🇹 Italy", "category": "MOTORSPORT"},
    {"name": "Franco Morbidelli", "team": "VR46 Racing", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇮🇹 Italy", "category": "MOTORSPORT"},
    {"name": "Fabio Di Giannantonio", "team": "VR46 Racing", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇮🇹 Italy", "category": "MOTORSPORT"},
    {"name": "Alex Márquez", "team": "Gresini Racing", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇪🇸 Spain", "category": "MOTORSPORT"},
    {"name": "Fermín Aldeguer", "team": "Gresini Racing", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇪🇸 Spain", "category": "MOTORSPORT"},

    # WRC Rally
    {"name": "Kalle Rovanperä", "team": "Toyota Gazoo Racing", "leagueId": "wrc", "leagueName": "WRC", "country": "🇫🇮 Finland", "category": "MOTORSPORT"},
    {"name": "Thierry Neuville", "team": "Hyundai Motorsport", "leagueId": "wrc", "leagueName": "WRC", "country": "🇧🇪 Belgium", "category": "MOTORSPORT"},
    {"name": "Sébastien Ogier", "team": "Toyota Gazoo Racing", "leagueId": "wrc", "leagueName": "WRC", "country": "🇫🇷 France", "category": "MOTORSPORT"},
    {"name": "Elfyn Evans", "team": "Toyota Gazoo Racing", "leagueId": "wrc", "leagueName": "WRC", "country": "🇬🇧 Great Britain", "category": "MOTORSPORT"},
    {"name": "Ott Tänak", "team": "Hyundai Motorsport", "leagueId": "wrc", "leagueName": "WRC", "country": "🇪🇪 Estonia", "category": "MOTORSPORT"},
    {"name": "Adrien Fourmaux", "team": "M-Sport Ford", "leagueId": "wrc", "leagueName": "WRC", "country": "🇫🇷 France", "category": "MOTORSPORT"},
    {"name": "Takamoto Katsuta", "team": "Toyota Gazoo Racing", "leagueId": "wrc", "leagueName": "WRC", "country": "🇯🇵 Japan", "category": "MOTORSPORT"},
    {"name": "Grégoire Munster", "team": "M-Sport Ford", "leagueId": "wrc", "leagueName": "WRC", "country": "🇱🇺 Luxembourg", "category": "MOTORSPORT"},
    {"name": "Sami Pajari", "team": "Toyota Gazoo Racing", "leagueId": "wrc", "leagueName": "WRC", "country": "🇫🇮 Finland", "category": "MOTORSPORT"},

    # IndyCar
    {"name": "Alex Palou", "team": "Chip Ganassi Racing", "leagueId": "ntt-indycar", "leagueName": "IndyCar", "country": "🇪🇸 Spain", "category": "MOTORSPORT"},
    {"name": "Will Power", "team": "Team Penske", "leagueId": "ntt-indycar", "leagueName": "IndyCar", "country": "🇦🇺 Australia", "category": "MOTORSPORT"},
    {"name": "Scott McLaughlin", "team": "Team Penske", "leagueId": "ntt-indycar", "leagueName": "IndyCar", "country": "🇳🇿 New Zealand", "category": "MOTORSPORT"},
    {"name": "Josef Newgarden", "team": "Team Penske", "leagueId": "ntt-indycar", "leagueName": "IndyCar", "country": "🇺🇸 USA", "category": "MOTORSPORT"},
    {"name": "Pato O'Ward", "team": "Arrow McLaren", "leagueId": "ntt-indycar", "leagueName": "IndyCar", "country": "🇲🇽 Mexico", "category": "MOTORSPORT"},
    {"name": "Scott Dixon", "team": "Chip Ganassi Racing", "leagueId": "ntt-indycar", "leagueName": "IndyCar", "country": "🇳🇿 New Zealand", "category": "MOTORSPORT"},
    {"name": "Colton Herta", "team": "Andretti Global", "leagueId": "ntt-indycar", "leagueName": "IndyCar", "country": "🇺🇸 USA", "category": "MOTORSPORT"},
    {"name": "Kyle Kirkwood", "team": "Andretti Global", "leagueId": "ntt-indycar", "leagueName": "IndyCar", "country": "🇺🇸 USA", "category": "MOTORSPORT"},
    {"name": "Marcus Armstrong", "team": "Meyer Shank Racing", "leagueId": "ntt-indycar", "leagueName": "IndyCar", "country": "🇳🇿 New Zealand", "category": "MOTORSPORT"},
    {"name": "Felix Rosenqvist", "team": "Meyer Shank Racing", "leagueId": "ntt-indycar", "leagueName": "IndyCar", "country": "🇸🇪 Sweden", "category": "MOTORSPORT"},

    # NASCAR Cup Series
    {"name": "Kyle Larson", "team": "Hendrick Motorsports", "leagueId": "nascar-cup", "leagueName": "NASCAR Cup", "country": "🇺🇸 USA", "category": "MOTORSPORT"},
    {"name": "Chase Elliott", "team": "Hendrick Motorsports", "leagueId": "nascar-cup", "leagueName": "NASCAR Cup", "country": "🇺🇸 USA", "category": "MOTORSPORT"},
    {"name": "William Byron", "team": "Hendrick Motorsports", "leagueId": "nascar-cup", "leagueName": "NASCAR Cup", "country": "🇺🇸 USA", "category": "MOTORSPORT"},
    {"name": "Ryan Blaney", "team": "Team Penske", "leagueId": "nascar-cup", "leagueName": "NASCAR Cup", "country": "🇺🇸 USA", "category": "MOTORSPORT"},
    {"name": "Joey Logano", "team": "Team Penske", "leagueId": "nascar-cup", "leagueName": "NASCAR Cup", "country": "🇺🇸 USA", "category": "MOTORSPORT"},
    {"name": "Denny Hamlin", "team": "Joe Gibbs Racing", "leagueId": "nascar-cup", "leagueName": "NASCAR Cup", "country": "🇺🇸 USA", "category": "MOTORSPORT"},
    {"name": "Christopher Bell", "team": "Joe Gibbs Racing", "leagueId": "nascar-cup", "leagueName": "NASCAR Cup", "country": "🇺🇸 USA", "category": "MOTORSPORT"},
    {"name": "Tyler Reddick", "team": "23XI Racing", "leagueId": "nascar-cup", "leagueName": "NASCAR Cup", "country": "🇺🇸 USA", "category": "MOTORSPORT"},
    {"name": "Bubba Wallace", "team": "23XI Racing", "leagueId": "nascar-cup", "leagueName": "NASCAR Cup", "country": "🇺🇸 USA", "category": "MOTORSPORT"},
    {"name": "Ross Chastain", "team": "Trackhouse Racing", "leagueId": "nascar-cup", "leagueName": "NASCAR Cup", "country": "🇺🇸 USA", "category": "MOTORSPORT"},
    {"name": "Shane van Gisbergen", "team": "Trackhouse Racing", "leagueId": "nascar-cup", "leagueName": "NASCAR Cup", "country": "🇳🇿 New Zealand", "category": "MOTORSPORT"}
]

# 2. Tennis Stars (ATP / WTA)
TENNIS_ATHLETES = [
    {"name": "Carlos Alcaraz", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇪🇸 Spain", "category": "TENNIS"},
    {"name": "Jannik Sinner", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇮🇹 Italy", "category": "TENNIS"},
    {"name": "Novak Djokovic", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇷🇸 Serbia", "category": "TENNIS"},
    {"name": "Daniil Medvedev", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇷🇺 Russia", "category": "TENNIS"},
    {"name": "Alexander Zverev", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇩🇪 Germany", "category": "TENNIS"},
    {"name": "Taylor Fritz", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇺🇸 USA", "category": "TENNIS"},
    {"name": "Casper Ruud", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇳🇴 Norway", "category": "TENNIS"},
    {"name": "Stefanos Tsitsipas", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇬🇷 Greece", "category": "TENNIS"},
    {"name": "Holger Rune", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇩🇰 Denmark", "category": "TENNIS"},
    {"name": "Grigor Dimitrov", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇧🇬 Bulgaria", "category": "TENNIS"},
    {"name": "Alex de Minaur", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇦🇺 Australia", "category": "TENNIS"},
    {"name": "Tommy Paul", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇺🇸 USA", "category": "TENNIS"},
    {"name": "Ben Shelton", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇺🇸 USA", "category": "TENNIS"},
    {"name": "Frances Tiafoe", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇺🇸 USA", "category": "TENNIS"},
    {"name": "Andrey Rublev", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇷🇺 Russia", "category": "TENNIS"},
    {"name": "Hubert Hurkacz", "team": "ATP Tour", "leagueId": "tennis-atp", "leagueName": "ATP Tour", "country": "🇵🇱 Poland", "category": "TENNIS"},
    {"name": "Aryna Sabalenka", "team": "WTA Tour", "leagueId": "tennis-wta", "leagueName": "WTA Tour", "country": "🇧🇾 Belarus", "category": "TENNIS"},
    {"name": "Iga Świątek", "team": "WTA Tour", "leagueId": "tennis-wta", "leagueName": "WTA Tour", "country": "🇵🇱 Poland", "category": "TENNIS"},
    {"name": "Coco Gauff", "team": "WTA Tour", "leagueId": "tennis-wta", "leagueName": "WTA Tour", "country": "🇺🇸 USA", "category": "TENNIS"},
    {"name": "Elena Rybakina", "team": "WTA Tour", "leagueId": "tennis-wta", "leagueName": "WTA Tour", "country": "🇰🇿 Kazakhstan", "category": "TENNIS"},
    {"name": "Jessica Pegula", "team": "WTA Tour", "leagueId": "tennis-wta", "leagueName": "WTA Tour", "country": "🇺🇸 USA", "category": "TENNIS"},
    {"name": "Jasmine Paolini", "team": "WTA Tour", "leagueId": "tennis-wta", "leagueName": "WTA Tour", "country": "🇮🇹 Italy", "category": "TENNIS"},
    {"name": "Qinwen Zheng", "team": "WTA Tour", "leagueId": "tennis-wta", "leagueName": "WTA Tour", "country": "🇨🇳 China", "category": "TENNIS"},
    {"name": "Emma Navarro", "team": "WTA Tour", "leagueId": "tennis-wta", "leagueName": "WTA Tour", "country": "🇺🇸 USA", "category": "TENNIS"},
    {"name": "Paula Badosa", "team": "WTA Tour", "leagueId": "tennis-wta", "leagueName": "WTA Tour", "country": "🇪🇸 Spain", "category": "TENNIS"}
]

# Supported Team Leagues that SportoCal has schedules for
LEAGUES_TO_SCRAPE = [
    ("soccer", "eng.1", "premierleague", "Premier League", "FOOTBALL"),
    ("soccer", "esp.1", "laliga", "La Liga", "FOOTBALL"),
    ("soccer", "ita.1", "seriea", "Serie A", "FOOTBALL"),
    ("soccer", "ger.1", "bundesliga", "Bundesliga", "FOOTBALL"),
    ("soccer", "fra.1", "soccer-fra.1", "Ligue 1", "FOOTBALL"),
    ("soccer", "usa.1", "mls", "MLS", "FOOTBALL"),
    ("soccer", "uefa.champions", "championsleague", "Champions League", "FOOTBALL"),
    ("basketball", "nba", "nba", "NBA", "BASKETBALL"),
    ("basketball", "wnba", "basketball-wnba", "WNBA", "BASKETBALL"),
    ("hockey", "nhl", "hockey-nhl", "NHL", "HOCKEY")
]

def scrape_team_roster(sport, league_slug, league_id, league_name, category, team_entry):
    team = team_entry.get('team', {})
    team_id = team.get('id')
    team_name = team.get('displayName') or team.get('name')
    if not team_id or not team_name:
        return []

    roster_url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_slug}/teams/{team_id}/roster"
    r_data = fetch_json(roster_url)
    if not r_data:
        return []

    raw_athletes = r_data.get('athletes', [])
    flat_athletes = []
    for entry in raw_athletes:
        if isinstance(entry, dict) and 'items' in entry:
            flat_athletes.extend(entry.get('items', []))
        elif isinstance(entry, dict):
            flat_athletes.append(entry)

    athletes = []
    for a in flat_athletes:
        name = a.get('displayName') or a.get('fullName')
        if not name or len(name) < 3:
            continue
        country_raw = a.get('citizenship') or a.get('birthPlace', {}).get('country') or a.get('birthCountry', {}).get('abbreviation') or ''
        athletes.append({
            'name': name.strip(),
            'team': team_name.strip(),
            'leagueId': league_id,
            'leagueName': league_name,
            'country': format_country(country_raw),
            'category': category
        })
    return athletes

def scrape_all_team_leagues():
    all_team_athletes = []
    for sport, league_slug, league_id, league_name, category in LEAGUES_TO_SCRAPE:
        print(f"Scraping team rosters for {league_name}...")
        teams_url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league_slug}/teams"
        data = fetch_json(teams_url)
        if not data:
            continue

        try:
            teams = data['sports'][0]['leagues'][0]['teams']
        except (KeyError, IndexError):
            continue

        def worker(team_entry):
            return scrape_team_roster(sport, league_slug, league_id, league_name, category, team_entry)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = pool.map(worker, teams)
            count = 0
            for r in results:
                all_team_athletes.extend(r)
                count += len(r)
            print(f"  -> {league_name}: {count} players collected across {len(teams)} teams.")

    return all_team_athletes

def extract_fighters_from_mma_events():
    """Scrapes UFC and PFL fighters listed on upcoming fight events."""
    fighters = []
    for mma_file in REPO_ROOT.glob("mma/**/*.json"):
        try:
            with open(mma_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                league_name = data.get("leagueName", "UFC")
                sport_key = data.get("sportKey", "mma-ufc")
                for event in data.get("events", []):
                    name = event.get("name", "")
                    match = re.search(r":\s*([A-Za-z\s]+)\s+(?:v|vs)\s+([A-Za-z\s]+)", name, re.IGNORECASE)
                    if match:
                        f1, f2 = match.group(1).strip(), match.group(2).strip()
                        if len(f1) > 2 and len(f2) > 2:
                            fighters.append({"name": f1, "team": league_name, "leagueId": sport_key, "leagueName": league_name, "country": "🌍 Global", "category": "MMA"})
                            fighters.append({"name": f2, "team": league_name, "leagueId": sport_key, "leagueName": league_name, "country": "🌍 Global", "category": "MMA"})
        except Exception:
            pass
    return fighters

def main():
    start_time = time.time()
    print("=== Starting SportoCal Full League Athlete Scraper ===")
    
    athletes_dict = {}

    # 1. Add Motorsport Drivers
    for a in MOTORSPORT_ATHLETES:
        athletes_dict[a["name"].lower()] = a

    # 2. Add Tennis Stars
    for a in TENNIS_ATHLETES:
        athletes_dict[a["name"].lower()] = a

    # 3. Add MMA Fighters from real events in app
    for a in extract_fighters_from_mma_events():
        if a["name"].lower() not in athletes_dict:
            athletes_dict[a["name"].lower()] = a

    # 4. Scrape all full squad rosters for all leagues tracked by the app
    team_athletes = scrape_all_team_leagues()
    for a in team_athletes:
        athletes_dict[a["name"].lower()] = a

    result = list(athletes_dict.values())
    result.sort(key=lambda x: (x["category"], x["name"]))

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Successfully generated {len(result)} total athletes to {OUTPUT_PATH}")
    print(f"Finished in {time.time() - start_time:.1f}s")

if __name__ == "__main__":
    main()
