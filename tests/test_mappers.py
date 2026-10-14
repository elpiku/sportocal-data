#!/usr/bin/env python3
"""
Unit tests for SportoCal data mappers across the three licensed providers:
1. API-Sports
2. football-data.org
3. BALLDONTLIE
"""

import sys
import unittest
from pathlib import Path

# Add scripts directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from api_sports_common import build_events_from_fixtures, extract_fixture_name, extract_date_from_fixture
from football_data_common import build_events_from_matches, _extract_match_name
from balldontlie_common import build_nba_events
from unified_models import Match, Team, matches_to_sportocal_data


class TestMappers(unittest.TestCase):

    def test_api_sports_mapper(self):
        sample_fixtures = [
            {
                "fixture": {
                    "id": 12345,
                    "date": "2026-08-15T16:30:00+00:00",
                },
                "league": {
                    "id": 61,
                    "name": "Ligue 1",
                    "round": "Regular Season - 1",
                },
                "teams": {
                    "home": {"id": 85, "name": "Paris Saint Germain", "code": "PSG"},
                    "away": {"id": 81, "name": "Marseille", "code": "MAR"},
                },
            }
        ]

        events = build_events_from_fixtures(sample_fixtures, id_prefix="l1", sport_key="football-ligue1")
        self.assertEqual(len(events), 1)
        event = events[0]

        self.assertEqual(event["name"], "Paris Saint Germain v Marseille")
        self.assertEqual(event["utc"], "2026-08-15T16:30:00Z")
        self.assertEqual(event["weekend"], "Regular Season - 1")
        self.assertTrue(event["id"].startswith("l1-2026-08-15-"))

    def test_football_data_mapper(self):
        sample_matches = [
            {
                "id": 4321,
                "utcDate": "2026-08-22T14:00:00Z",
                "status": "SCHEDULED",
                "matchday": 2,
                "homeTeam": {"id": 57, "name": "Arsenal FC", "shortName": "Arsenal"},
                "awayTeam": {"id": 65, "name": "Manchester City FC", "shortName": "Man City"},
            }
        ]

        events = build_events_from_matches(sample_matches, id_prefix="pl")
        self.assertEqual(len(events), 1)
        event = events[0]

        self.assertEqual(event["name"], "Arsenal v Man City")
        self.assertEqual(event["utc"], "2026-08-22T14:00:00Z")
        self.assertEqual(event["weekend"], "Matchday 2")
        self.assertTrue(event["id"].startswith("pl-2026-08-22-"))

    def test_balldontlie_mapper(self):
        sample_games = [
            {
                "id": 999,
                "date": "2026-10-25",
                "season": 2026,
                "status": "Final",
                "period": 4,
                "home_team": {
                    "id": 14,
                    "full_name": "Los Angeles Lakers",
                    "abbreviation": "LAL",
                },
                "visitor_team": {
                    "id": 2,
                    "full_name": "Boston Celtics",
                    "abbreviation": "BOS",
                },
            }
        ]

        events = build_nba_events(sample_games, id_prefix="nba")
        self.assertEqual(len(events), 1)
        event = events[0]

        self.assertEqual(event["name"], "Boston Celtics v Los Angeles Lakers")
        self.assertTrue(event["utc"].startswith("2026-10-25T"))
        self.assertEqual(event["weekend"], "Season 2026")
        self.assertTrue(event["id"].startswith("nba-2026-10-25-"))

    def test_unified_model_export(self):
        matches = [
            Match(
                id="match-1",
                name="Team A v Team B",
                utc="2026-09-01T18:00:00Z",
                sport="football",
                league_id="2021",
                league_name="Premier League",
                weekend="Matchday 1",
            )
        ]
        doc = matches_to_sportocal_data(
            matches,
            sport_key="premierleague",
            league_name="Premier League",
            date_from="2026-08-01",
            date_to="2027-05-31",
            season="2026-27",
        )
        self.assertEqual(doc["sportKey"], "premierleague")
        self.assertEqual(doc["leagueName"], "Premier League")
        self.assertEqual(doc["season"], "2026-27")
        self.assertEqual(doc["windowFrom"], "20260801")
        self.assertEqual(doc["windowTo"], "20270531")
        self.assertEqual(len(doc["events"]), 1)
        self.assertEqual(doc["events"][0]["name"], "Team A v Team B")


if __name__ == "__main__":
    unittest.main()
