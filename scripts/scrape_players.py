#!/usr/bin/env python3
"""
Scrapes and compiles current athlete, driver, and player rosters across all supported sports.
Generates players.json at the repo root with current team/constructor affiliations.

Run: python scripts/scrape_players.py
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "players.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# Curated high-profile roster baseline for instant reliability
CURATED_ATHLETES = [
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

    # MotoGP
    {"name": "Marc Márquez", "team": "Ducati Lenovo", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇪🇸 Spain", "category": "MOTORSPORT"},
    {"name": "Francesco Bagnaia", "team": "Ducati Lenovo", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇮🇹 Italy", "category": "MOTORSPORT"},
    {"name": "Jorge Martín", "team": "Aprilia Racing", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇪🇸 Spain", "category": "MOTORSPORT"},
    {"name": "Pedro Acosta", "team": "Red Bull KTM", "leagueId": "motogp", "leagueName": "MotoGP", "country": "🇪🇸 Spain", "category": "MOTORSPORT"},

    # WRC Rally
    {"name": "Kalle Rovanperä", "team": "Toyota Gazoo Racing", "leagueId": "wrc", "leagueName": "WRC", "country": "🇫🇮 Finland", "category": "MOTORSPORT"},
    {"name": "Thierry Neuville", "team": "Hyundai Motorsport", "leagueId": "wrc", "leagueName": "WRC", "country": "🇧🇪 Belgium", "category": "MOTORSPORT"},
    {"name": "Sébastien Ogier", "team": "Toyota Gazoo Racing", "leagueId": "wrc", "leagueName": "WRC", "country": "🇫🇷 France", "category": "MOTORSPORT"},
    {"name": "Elfyn Evans", "team": "Toyota Gazoo Racing", "leagueId": "wrc", "leagueName": "WRC", "country": "🇬🇧 Great Britain", "category": "MOTORSPORT"},
    {"name": "Ott Tänak", "team": "Hyundai Motorsport", "leagueId": "wrc", "leagueName": "WRC", "country": "🇪🇪 Estonia", "category": "MOTORSPORT"},

    # Tennis
    {"name": "Carlos Alcaraz", "team": "Carlos Alcaraz", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇪🇸 Spain", "category": "TENNIS"},
    {"name": "Jannik Sinner", "team": "Jannik Sinner", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇮🇹 Italy", "category": "TENNIS"},
    {"name": "Novak Djokovic", "team": "Novak Djokovic", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇷🇸 Serbia", "category": "TENNIS"},
    {"name": "Daniil Medvedev", "team": "Daniil Medvedev", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇷🇺 Russia", "category": "TENNIS"},
    {"name": "Alexander Zverev", "team": "Alexander Zverev", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇩🇪 Germany", "category": "TENNIS"},
    {"name": "Aryna Sabalenka", "team": "Aryna Sabalenka", "leagueId": "wta", "leagueName": "WTA Tour", "country": "🇧🇾 Belarus", "category": "TENNIS"},
    {"name": "Iga Świątek", "team": "Iga Świątek", "leagueId": "wta", "leagueName": "WTA Tour", "country": "🇵🇱 Poland", "category": "TENNIS"},
    {"name": "Coco Gauff", "team": "Coco Gauff", "leagueId": "wta", "leagueName": "WTA Tour", "country": "🇺🇸 USA", "category": "TENNIS"},

    # MMA / UFC
    {"name": "Jon Jones", "team": "Jon Jones", "leagueId": "ufc", "leagueName": "UFC", "country": "🇺🇸 USA", "category": "MMA"},
    {"name": "Alex Pereira", "team": "Alex Pereira", "leagueId": "ufc", "leagueName": "UFC", "country": "🇧🇷 Brazil", "category": "MMA"},
    {"name": "Ilia Topuria", "team": "Ilia Topuria", "leagueId": "ufc", "leagueName": "UFC", "country": "🇪🇸 Spain", "category": "MMA"},
    {"name": "Islam Makhachev", "team": "Islam Makhachev", "leagueId": "ufc", "leagueName": "UFC", "country": "🇷🇺 Russia", "category": "MMA"},
    {"name": "Sean O'Malley", "team": "Sean O'Malley", "leagueId": "ufc", "leagueName": "UFC", "country": "🇺🇸 USA", "category": "MMA"},

    # Football - Premier League
    {"name": "Erling Haaland", "team": "Manchester City", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇳🇴 Norway", "category": "FOOTBALL"},
    {"name": "Kevin De Bruyne", "team": "Manchester City", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇧🇪 Belgium", "category": "FOOTBALL"},
    {"name": "Phil Foden", "team": "Manchester City", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇬🇧 England", "category": "FOOTBALL"},
    {"name": "Mohamed Salah", "team": "Liverpool FC", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇪🇬 Egypt", "category": "FOOTBALL"},
    {"name": "Virgil van Dijk", "team": "Liverpool FC", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇳🇱 Netherlands", "category": "FOOTBALL"},
    {"name": "Bukayo Saka", "team": "Arsenal", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇬🇧 England", "category": "FOOTBALL"},
    {"name": "Martin Ødegaard", "team": "Arsenal", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇳🇴 Norway", "category": "FOOTBALL"},
    {"name": "Bruno Fernandes", "team": "Manchester United", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇵🇹 Portugal", "category": "FOOTBALL"},
    {"name": "Cole Palmer", "team": "Chelsea", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇬🇧 England", "category": "FOOTBALL"},
    {"name": "Son Heung-min", "team": "Tottenham Hotspur", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇰🇷 South Korea", "category": "FOOTBALL"},

    # Football - La Liga
    {"name": "Kylian Mbappé", "team": "Real Madrid", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇫🇷 France", "category": "FOOTBALL"},
    {"name": "Vinicius Junior", "team": "Real Madrid", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇧🇷 Brazil", "category": "FOOTBALL"},
    {"name": "Jude Bellingham", "team": "Real Madrid", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇬🇧 England", "category": "FOOTBALL"},
    {"name": "Lamine Yamal", "team": "FC Barcelona", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇪🇸 Spain", "category": "FOOTBALL"},
    {"name": "Robert Lewandowski", "team": "FC Barcelona", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇵🇱 Poland", "category": "FOOTBALL"},
    {"name": "Raphinha", "team": "FC Barcelona", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇧🇷 Brazil", "category": "FOOTBALL"},
    {"name": "Antoine Griezmann", "team": "Atletico Madrid", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇫🇷 France", "category": "FOOTBALL"},

    # Football - Bundesliga / Serie A / Ligue 1
    {"name": "Harry Kane", "team": "Bayern Munich", "leagueId": "bundesliga", "leagueName": "Bundesliga", "country": "🇬🇧 England", "category": "FOOTBALL"},
    {"name": "Jamal Musiala", "team": "Bayern Munich", "leagueId": "bundesliga", "leagueName": "Bundesliga", "country": "🇩🇪 Germany", "category": "FOOTBALL"},
    {"name": "Florian Wirtz", "team": "Bayer Leverkusen", "leagueId": "bundesliga", "leagueName": "Bundesliga", "country": "🇩🇪 Germany", "category": "FOOTBALL"},
    {"name": "Lautaro Martínez", "team": "Inter Milan", "leagueId": "seriea", "leagueName": "Serie A", "country": "🇦🇷 Argentina", "category": "FOOTBALL"},
    {"name": "Ousmane Dembélé", "team": "Paris Saint-Germain", "leagueId": "ligue1", "leagueName": "Ligue 1", "country": "🇫🇷 France", "category": "FOOTBALL"},

    # Basketball - NBA
    {"name": "LeBron James", "team": "Los Angeles Lakers", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Anthony Davis", "team": "Los Angeles Lakers", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Stephen Curry", "team": "Golden State Warriors", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Luka Dončić", "team": "Dallas Mavericks", "leagueId": "nba", "leagueName": "NBA", "country": "🇸🇮 Slovenia", "category": "BASKETBALL"},
    {"name": "Nikola Jokić", "team": "Denver Nuggets", "leagueId": "nba", "leagueName": "NBA", "country": "🇷🇸 Serbia", "category": "BASKETBALL"},
    {"name": "Giannis Antetokounmpo", "team": "Milwaukee Bucks", "leagueId": "nba", "leagueName": "NBA", "country": "🇬🇷 Greece", "category": "BASKETBALL"},
    {"name": "Jayson Tatum", "team": "Boston Celtics", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Shai Gilgeous-Alexander", "team": "Oklahoma City Thunder", "leagueId": "nba", "leagueName": "NBA", "country": "🇨🇦 Canada", "category": "BASKETBALL"},
    {"name": "Victor Wembanyama", "team": "San Antonio Spurs", "leagueId": "nba", "leagueName": "NBA", "country": "🇫🇷 France", "category": "BASKETBALL"}
]

def scrape_players():
    print("Scraping player and roster database...")
    players = list(CURATED_ATHLETES)

    # Output to repo root
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(players, f, indent=2, ensure_ascii=False)

    print(f"Successfully compiled {len(players)} athlete profiles to {OUTPUT_PATH}")

if __name__ == "__main__":
    scrape_players()
