#!/usr/bin/env python3
"""
Unified Data Layer for SportoCal data scrapers.

Defines provider-independent models (Match, Team, League, Player, Standing)
and the SportsProvider abstract base class.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class Team:
    """Provider-independent team model."""
    id: str
    name: str
    short_name: Optional[str] = None
    code: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "shortName": self.short_name,
            "code": self.code,
        }


@dataclass
class Match:
    """
    Provider-independent match/event model.
    Maps directly to SportoCal event schema:
      {"id": str, "weekend": str, "name": str, "utc": str}
    """
    id: str
    name: str
    utc: str
    sport: str
    league_id: str
    league_name: str
    weekend: Optional[str] = None
    status: Optional[str] = None
    home_team: Optional[Team] = None
    away_team: Optional[Team] = None

    def to_sportocal_event(self) -> dict[str, str]:
        """Convert to the standard event dictionary consumed by SportoCal."""
        return {
            "id": self.id,
            "weekend": self.weekend or (self.utc[:10] if self.utc else ""),
            "name": self.name,
            "utc": self.utc,
        }


@dataclass
class League:
    """Provider-independent league/competition model."""
    id: str
    name: str
    sport: str
    country: Optional[str] = None
    season: Optional[str] = None


@dataclass
class Standing:
    """Provider-independent standing/table row model."""
    league_id: str
    team: Team
    position: int
    points: int
    played: int
    won: int
    drawn: int
    lost: int


@dataclass
class Player:
    """Provider-independent athlete/player model."""
    name: str
    team: str
    league_id: str
    league_name: str
    country: str
    category: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "team": self.team,
            "leagueId": self.league_id,
            "leagueName": self.league_name,
            "country": self.country,
            "category": self.category,
        }


class SportsProvider(ABC):
    """Abstract base class for all sports data providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g. 'api-sports', 'football-data', 'balldontlie')."""
        pass

    @abstractmethod
    def get_matches_by_date(self, sport: str, date: str) -> list[Match]:
        """
        Fetch matches on a specific date (YYYY-MM-DD).
        """
        pass

    @abstractmethod
    def get_live_matches(self, sport: str) -> list[Match]:
        """
        Fetch matches currently in progress for the specified sport.
        """
        pass

    @abstractmethod
    def get_league_matches(
        self, league_id: Any, date_from: str, date_to: str, sport: str = "football"
    ) -> list[Match]:
        """
        Fetch matches for a specific league within a date range (YYYY-MM-DD).
        """
        pass


def matches_to_sportocal_data(
    matches: list[Match],
    sport_key: str,
    league_name: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    season: Optional[str] = None,
) -> dict[str, Any]:
    """
    Format a list of unified Match objects into the standard SportoCal JSON document.
    """
    events = [m.to_sportocal_event() for m in matches]
    events.sort(key=lambda x: x["utc"])

    data: dict[str, Any] = {
        "sportKey": sport_key,
        "leagueName": league_name,
    }
    if season:
        data["season"] = season
    if date_from:
        data["windowFrom"] = date_from.replace("-", "")
    if date_to:
        data["windowTo"] = date_to.replace("-", "")

    data["events"] = events
    return data
