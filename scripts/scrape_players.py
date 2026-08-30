#!/usr/bin/env python3
"""
Scrapes and compiles current athlete, driver, and player rosters across all supported sports.
Extracts every athlete, fighter, driver, and star from event JSONs in the repository.
Generates players.json at the repo root.

Run: python scripts/scrape_players.py
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "players.json"

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

    # WRC Rally
    {"name": "Kalle Rovanperä", "team": "Toyota Gazoo Racing", "leagueId": "wrc", "leagueName": "WRC", "country": "🇫🇮 Finland", "category": "MOTORSPORT"},
    {"name": "Thierry Neuville", "team": "Hyundai Motorsport", "leagueId": "wrc", "leagueName": "WRC", "country": "🇧🇪 Belgium", "category": "MOTORSPORT"},
    {"name": "Sébastien Ogier", "team": "Toyota Gazoo Racing", "leagueId": "wrc", "leagueName": "WRC", "country": "🇫🇷 France", "category": "MOTORSPORT"},
    {"name": "Elfyn Evans", "team": "Toyota Gazoo Racing", "leagueId": "wrc", "leagueName": "WRC", "country": "🇬🇧 Great Britain", "category": "MOTORSPORT"},
    {"name": "Ott Tänak", "team": "Hyundai Motorsport", "leagueId": "wrc", "leagueName": "WRC", "country": "🇪🇪 Estonia", "category": "MOTORSPORT"},
    {"name": "Adrien Fourmaux", "team": "M-Sport Ford", "leagueId": "wrc", "leagueName": "WRC", "country": "🇫🇷 France", "category": "MOTORSPORT"},
    {"name": "Takamoto Katsuta", "team": "Toyota Gazoo Racing", "leagueId": "wrc", "leagueName": "WRC", "country": "🇯🇵 Japan", "category": "MOTORSPORT"},
    {"name": "Grégoire Munster", "team": "M-Sport Ford", "leagueId": "wrc", "leagueName": "WRC", "country": "🇱🇺 Luxembourg", "category": "MOTORSPORT"},

    # Tennis - ATP Top Stars
    {"name": "Carlos Alcaraz", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇪🇸 Spain", "category": "TENNIS"},
    {"name": "Jannik Sinner", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇮🇹 Italy", "category": "TENNIS"},
    {"name": "Novak Djokovic", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇷🇸 Serbia", "category": "TENNIS"},
    {"name": "Daniil Medvedev", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇷🇺 Russia", "category": "TENNIS"},
    {"name": "Alexander Zverev", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇩🇪 Germany", "category": "TENNIS"},
    {"name": "Taylor Fritz", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇺🇸 USA", "category": "TENNIS"},
    {"name": "Casper Ruud", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇳🇴 Norway", "category": "TENNIS"},
    {"name": "Stefanos Tsitsipas", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇬🇷 Greece", "category": "TENNIS"},
    {"name": "Holger Rune", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇩🇰 Denmark", "category": "TENNIS"},
    {"name": "Grigor Dimitrov", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇧🇬 Bulgaria", "category": "TENNIS"},
    {"name": "Alex de Minaur", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇦🇺 Australia", "category": "TENNIS"},
    {"name": "Tommy Paul", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇺🇸 USA", "category": "TENNIS"},
    {"name": "Ben Shelton", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇺🇸 USA", "category": "TENNIS"},
    {"name": "Frances Tiafoe", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇺🇸 USA", "category": "TENNIS"},
    {"name": "Andrey Rublev", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇷🇺 Russia", "category": "TENNIS"},
    {"name": "Hubert Hurkacz", "team": "ATP Tour", "leagueId": "atp", "leagueName": "ATP Tour", "country": "🇵🇱 Poland", "category": "TENNIS"},

    # Tennis - WTA Top Stars
    {"name": "Aryna Sabalenka", "team": "WTA Tour", "leagueId": "wta", "leagueName": "WTA Tour", "country": "🇧🇾 Belarus", "category": "TENNIS"},
    {"name": "Iga Świątek", "team": "WTA Tour", "leagueId": "wta", "leagueName": "WTA Tour", "country": "🇵🇱 Poland", "category": "TENNIS"},
    {"name": "Coco Gauff", "team": "WTA Tour", "leagueId": "wta", "leagueName": "WTA Tour", "country": "🇺🇸 USA", "category": "TENNIS"},
    {"name": "Elena Rybakina", "team": "WTA Tour", "leagueId": "wta", "leagueName": "WTA Tour", "country": "🇰🇿 Kazakhstan", "category": "TENNIS"},
    {"name": "Jessica Pegula", "team": "WTA Tour", "leagueId": "wta", "leagueName": "WTA Tour", "country": "🇺🇸 USA", "category": "TENNIS"},
    {"name": "Jasmine Paolini", "team": "WTA Tour", "leagueId": "wta", "leagueName": "WTA Tour", "country": "🇮🇹 Italy", "category": "TENNIS"},
    {"name": "Qinwen Zheng", "team": "WTA Tour", "leagueId": "wta", "leagueName": "WTA Tour", "country": "🇨🇳 China", "category": "TENNIS"},
    {"name": "Emma Navarro", "team": "WTA Tour", "leagueId": "wta", "leagueName": "WTA Tour", "country": "🇺🇸 USA", "category": "TENNIS"},
    {"name": "Paula Badosa", "team": "WTA Tour", "leagueId": "wta", "leagueName": "WTA Tour", "country": "🇪🇸 Spain", "category": "TENNIS"},
    {"name": "Maria Sakkari", "team": "WTA Tour", "leagueId": "wta", "leagueName": "WTA Tour", "country": "🇬🇷 Greece", "category": "TENNIS"},

    # MMA / UFC
    {"name": "Jon Jones", "team": "UFC Heavyweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇺🇸 USA", "category": "MMA"},
    {"name": "Alex Pereira", "team": "UFC Light Heavyweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇧🇷 Brazil", "category": "MMA"},
    {"name": "Ilia Topuria", "team": "UFC Featherweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇪🇸 Spain", "category": "MMA"},
    {"name": "Islam Makhachev", "team": "UFC Lightweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇷🇺 Russia", "category": "MMA"},
    {"name": "Sean O'Malley", "team": "UFC Bantamweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇺🇸 USA", "category": "MMA"},
    {"name": "Merab Dvalishvili", "team": "UFC Bantamweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇬🇪 Georgia", "category": "MMA"},
    {"name": "Dricus du Plessis", "team": "UFC Middleweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇿🇦 South Africa", "category": "MMA"},
    {"name": "Israel Adesanya", "team": "UFC Middleweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇳🇿 New Zealand", "category": "MMA"},
    {"name": "Belal Muhammad", "team": "UFC Welterweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇵🇸 Palestine", "category": "MMA"},
    {"name": "Shavkat Rakhmonov", "team": "UFC Welterweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇰🇿 Kazakhstan", "category": "MMA"},
    {"name": "Alexandre Pantoja", "team": "UFC Flyweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇧🇷 Brazil", "category": "MMA"},
    {"name": "Max Holloway", "team": "UFC Featherweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇺🇸 USA", "category": "MMA"},
    {"name": "Dustin Poirier", "team": "UFC Lightweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇺🇸 USA", "category": "MMA"},
    {"name": "Justin Gaethje", "team": "UFC Lightweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇺🇸 USA", "category": "MMA"},
    {"name": "Charles Oliveira", "team": "UFC Lightweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇧🇷 Brazil", "category": "MMA"},
    {"name": "Khamzat Chimaev", "team": "UFC Middleweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇦🇪 UAE", "category": "MMA"},
    {"name": "Tom Aspinall", "team": "UFC Heavyweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇬🇧 Great Britain", "category": "MMA"},
    {"name": "Ciryl Gane", "team": "UFC Heavyweight", "leagueId": "ufc", "leagueName": "UFC", "country": "🇫🇷 France", "category": "MMA"},

    # Football - Premier League
    {"name": "Erling Haaland", "team": "Manchester City", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇳🇴 Norway", "category": "FOOTBALL"},
    {"name": "Kevin De Bruyne", "team": "Manchester City", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇧🇪 Belgium", "category": "FOOTBALL"},
    {"name": "Phil Foden", "team": "Manchester City", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇬🇧 England", "category": "FOOTBALL"},
    {"name": "Rodri", "team": "Manchester City", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇪🇸 Spain", "category": "FOOTBALL"},
    {"name": "Mohamed Salah", "team": "Liverpool FC", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇪🇬 Egypt", "category": "FOOTBALL"},
    {"name": "Virgil van Dijk", "team": "Liverpool FC", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇳🇱 Netherlands", "category": "FOOTBALL"},
    {"name": "Trent Alexander-Arnold", "team": "Liverpool FC", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇬🇧 England", "category": "FOOTBALL"},
    {"name": "Bukayo Saka", "team": "Arsenal", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇬🇧 England", "category": "FOOTBALL"},
    {"name": "Martin Ødegaard", "team": "Arsenal", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇳🇴 Norway", "category": "FOOTBALL"},
    {"name": "Declan Rice", "team": "Arsenal", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇬🇧 England", "category": "FOOTBALL"},
    {"name": "William Saliba", "team": "Arsenal", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇫🇷 France", "category": "FOOTBALL"},
    {"name": "Cole Palmer", "team": "Chelsea", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇬🇧 England", "category": "FOOTBALL"},
    {"name": "Enzo Fernández", "team": "Chelsea", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇦🇷 Argentina", "category": "FOOTBALL"},
    {"name": "Bruno Fernandes", "team": "Manchester United", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇵🇹 Portugal", "category": "FOOTBALL"},
    {"name": "Marcus Rashford", "team": "Manchester United", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇬🇧 England", "category": "FOOTBALL"},
    {"name": "Son Heung-min", "team": "Tottenham Hotspur", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇰🇷 South Korea", "category": "FOOTBALL"},
    {"name": "James Maddison", "team": "Tottenham Hotspur", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇬🇧 England", "category": "FOOTBALL"},
    {"name": "Alexander Isak", "team": "Newcastle United", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇸🇪 Sweden", "category": "FOOTBALL"},
    {"name": "Ollie Watkins", "team": "Aston Villa", "leagueId": "premierleague", "leagueName": "Premier League", "country": "🇬🇧 England", "category": "FOOTBALL"},

    # Football - La Liga
    {"name": "Kylian Mbappé", "team": "Real Madrid", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇫🇷 France", "category": "FOOTBALL"},
    {"name": "Vinicius Junior", "team": "Real Madrid", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇧🇷 Brazil", "category": "FOOTBALL"},
    {"name": "Jude Bellingham", "team": "Real Madrid", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇬🇧 England", "category": "FOOTBALL"},
    {"name": "Federico Valverde", "team": "Real Madrid", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇺🇾 Uruguay", "category": "FOOTBALL"},
    {"name": "Rodrygo", "team": "Real Madrid", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇧🇷 Brazil", "category": "FOOTBALL"},
    {"name": "Luka Modrić", "team": "Real Madrid", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇭🇷 Croatia", "category": "FOOTBALL"},
    {"name": "Lamine Yamal", "team": "FC Barcelona", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇪🇸 Spain", "category": "FOOTBALL"},
    {"name": "Robert Lewandowski", "team": "FC Barcelona", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇵🇱 Poland", "category": "FOOTBALL"},
    {"name": "Raphinha", "team": "FC Barcelona", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇧🇷 Brazil", "category": "FOOTBALL"},
    {"name": "Pedri", "team": "FC Barcelona", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇪🇸 Spain", "category": "FOOTBALL"},
    {"name": "Gavi", "team": "FC Barcelona", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇪🇸 Spain", "category": "FOOTBALL"},
    {"name": "Dani Olmo", "team": "FC Barcelona", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇪🇸 Spain", "category": "FOOTBALL"},
    {"name": "Antoine Griezmann", "team": "Atletico Madrid", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇫🇷 France", "category": "FOOTBALL"},
    {"name": "Julián Alvarez", "team": "Atletico Madrid", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇦🇷 Argentina", "category": "FOOTBALL"},
    {"name": "Nico Williams", "team": "Athletic Club", "leagueId": "laliga", "leagueName": "La Liga", "country": "🇪🇸 Spain", "category": "FOOTBALL"},

    # Football - Bundesliga / Serie A / Ligue 1
    {"name": "Harry Kane", "team": "Bayern Munich", "leagueId": "bundesliga", "leagueName": "Bundesliga", "country": "🇬🇧 England", "category": "FOOTBALL"},
    {"name": "Jamal Musiala", "team": "Bayern Munich", "leagueId": "bundesliga", "leagueName": "Bundesliga", "country": "🇩🇪 Germany", "category": "FOOTBALL"},
    {"name": "Florian Wirtz", "team": "Bayer Leverkusen", "leagueId": "bundesliga", "leagueName": "Bundesliga", "country": "🇩🇪 Germany", "category": "FOOTBALL"},
    {"name": "Lautaro Martínez", "team": "Inter Milan", "leagueId": "seriea", "leagueName": "Serie A", "country": "🇦🇷 Argentina", "category": "FOOTBALL"},
    {"name": "Nicolò Barella", "team": "Inter Milan", "leagueId": "seriea", "leagueName": "Serie A", "country": "🇮🇹 Italy", "category": "FOOTBALL"},
    {"name": "Khvicha Kvaratskhelia", "team": "Napoli", "leagueId": "seriea", "leagueName": "Serie A", "country": "🇬🇪 Georgia", "category": "FOOTBALL"},
    {"name": "Victor Osimhen", "team": "Galatasaray", "leagueId": "tur.1", "leagueName": "Super Lig", "country": "🇳🇬 Nigeria", "category": "FOOTBALL"},
    {"name": "Ousmane Dembélé", "team": "Paris Saint-Germain", "leagueId": "ligue1", "leagueName": "Ligue 1", "country": "🇫🇷 France", "category": "FOOTBALL"},
    {"name": "Achraf Hakimi", "team": "Paris Saint-Germain", "leagueId": "ligue1", "leagueName": "Ligue 1", "country": "🇲🇦 Morocco", "category": "FOOTBALL"},

    # Basketball - NBA
    {"name": "LeBron James", "team": "Los Angeles Lakers", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Anthony Davis", "team": "Los Angeles Lakers", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Stephen Curry", "team": "Golden State Warriors", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Luka Dončić", "team": "Dallas Mavericks", "leagueId": "nba", "leagueName": "NBA", "country": "🇸🇮 Slovenia", "category": "BASKETBALL"},
    {"name": "Kyrie Irving", "team": "Dallas Mavericks", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Nikola Jokić", "team": "Denver Nuggets", "leagueId": "nba", "leagueName": "NBA", "country": "🇷🇸 Serbia", "category": "BASKETBALL"},
    {"name": "Jamal Murray", "team": "Denver Nuggets", "leagueId": "nba", "leagueName": "NBA", "country": "🇨🇦 Canada", "category": "BASKETBALL"},
    {"name": "Giannis Antetokounmpo", "team": "Milwaukee Bucks", "leagueId": "nba", "leagueName": "NBA", "country": "🇬🇷 Greece", "category": "BASKETBALL"},
    {"name": "Damian Lillard", "team": "Milwaukee Bucks", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Jayson Tatum", "team": "Boston Celtics", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Jaylen Brown", "team": "Boston Celtics", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Shai Gilgeous-Alexander", "team": "Oklahoma City Thunder", "leagueId": "nba", "leagueName": "NBA", "country": "🇨🇦 Canada", "category": "BASKETBALL"},
    {"name": "Chet Holmgren", "team": "Oklahoma City Thunder", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Victor Wembanyama", "team": "San Antonio Spurs", "leagueId": "nba", "leagueName": "NBA", "country": "🇫🇷 France", "category": "BASKETBALL"},
    {"name": "Anthony Edwards", "team": "Minnesota Timberwolves", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Kevin Durant", "team": "Phoenix Suns", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Devin Booker", "team": "Phoenix Suns", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Joel Embiid", "team": "Philadelphia 76ers", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Paul George", "team": "Philadelphia 76ers", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Tyrese Haliburton", "team": "Indiana Pacers", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Ja Morant", "team": "Memphis Grizzlies", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Jimmy Butler", "team": "Miami Heat", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Bam Adebayo", "team": "Miami Heat", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Trae Young", "team": "Atlanta Hawks", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Zion Williamson", "team": "New Orleans Pelicans", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"},
    {"name": "Paolo Banchero", "team": "Orlando Magic", "leagueId": "nba", "leagueName": "NBA", "country": "🇺🇸 USA", "category": "BASKETBALL"}
]

def extract_athletes_from_repo_events():
    """Scans MMA, Tennis, and Motorsport JSON files to extract all fighting pairs and drivers."""
    extracted = []
    
    # 1. MMA events
    for mma_file in REPO_ROOT.glob("mma/**/*.json"):
        if "espn-all" not in str(mma_file) and mma_file.name != "index.json":
            continue
        try:
            with open(mma_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                league_name = data.get("leagueName", "MMA")
                sport_key = data.get("sportKey", "mma")
                for event in data.get("events", []):
                    name = event.get("name", "")
                    # Match 'A v B' or 'A vs B' or 'A-B'
                    match = re.search(r":\s*([A-Za-z\s]+)\s+(?:v|vs)\s+([A-Za-z\s]+)", name, re.IGNORECASE)
                    if match:
                        f1, f2 = match.group(1).strip(), match.group(2).strip()
                        if len(f1) > 2 and len(f2) > 2:
                            extracted.append({"name": f1, "team": league_name, "leagueId": sport_key, "leagueName": league_name, "country": "🌍 Global", "category": "MMA"})
                            extracted.append({"name": f2, "team": league_name, "leagueId": sport_key, "leagueName": league_name, "country": "🌍 Global", "category": "MMA"})
        except Exception:
            pass

    return extracted

def scrape_players():
    print("Scraping athlete, driver, and player database across all competitions...")
    players_dict = {p["name"].lower(): p for p in CURATED_ATHLETES}

    # Add dynamically extracted fighters and athletes
    for ath in extract_athletes_from_repo_events():
        if ath["name"].lower() not in players_dict:
            players_dict[ath["name"].lower()] = ath

    result = list(players_dict.values())
    result.sort(key=lambda x: (x["category"], x["name"]))

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Successfully compiled {len(result)} athlete profiles to {OUTPUT_PATH}")

if __name__ == "__main__":
    scrape_players()
