"""API-Football v3 client — single data source for all analysis.

Requires FOOTBALL_API_KEY environment variable.
Uses API-Sports direct platform (https://v3.football.api-sports.io/).

Rate limit: 100 requests/day on free tier.
On rate limit hit, raises RateLimitError — no fallback, no downgrade.
Register at: https://dashboard.api-football.com/register
"""

import os
import time
import requests
from typing import Any, Optional

from utils import RateLimitError

BASE_URL = "https://v3.football.api-sports.io"


def _headers() -> dict[str, str]:
    key = os.environ.get("FOOTBALL_API_KEY", "")
    if not key:
        raise RuntimeError("FOOTBALL_API_KEY environment variable not set")
    return {"x-apisports-key": key}


def _get(endpoint: str, params: Optional[dict[str, Any]] = None) -> dict:
    """Make a GET request to API-Football v3.

    Returns the 'response' list from the API. Raises RateLimitError on 429.  
    """
    url = f"{BASE_URL}/{endpoint}"
    resp = requests.get(url, headers=_headers(), params=params or {})
    
    if resp.status_code == 429:
        raise RateLimitError("API rate limit reached. Upgrade plan for more requests.")
    
    if resp.status_code != 200:
        body = resp.text[:300]
        raise RuntimeError(f"API returned {resp.status_code}: {body}")
    
    data = resp.json()
    if data.get("errors"):
        errors = data["errors"]
        # Some errors come as dict, some as list
        msg = str(errors)
        raise RuntimeError(f"API errors: {msg}")
    
    return data


def get_fixtures(league_id: int, season: int, 
                 team_id: Optional[int] = None,
                 status: Optional[str] = None,
                 from_date: Optional[str] = None,
                 to_date: Optional[str] = None) -> list[dict]:
    """Get fixtures for a league/season. Filter by team, status, or date range."""
    params: dict[str, Any] = {"league": league_id, "season": season}
    if team_id:
        params["team"] = team_id
    if status:
        params["status"] = status
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    return _get("fixtures", params).get("response", [])


def get_fixture_by_id(fixture_id: int) -> dict:
    """Get a single fixture with all details (events, lineups, stats, players)."""
    params = {"id": fixture_id}
    return _get("fixtures", params).get("response", [])


def get_fixtures_head2head(h2h: str) -> list[dict]:
    """Get head-to-head fixtures between two teams. h2h format: 'teamId1-teamId2'."""
    return _get("fixtures/headtohead", {"h2h": h2h}).get("response", [])


def get_odds(fixture_id: Optional[int] = None,
             league_id: Optional[int] = None,
             season: Optional[int] = None,
             bookmaker: Optional[int] = None,
             bet: Optional[int] = None,
             page: int = 1) -> list[dict]:
    """Get pre-match odds. Filter by fixture, league, bookmaker, or bet type."""
    params: dict[str, Any] = {"page": page}
    if fixture_id:
        params["fixture"] = fixture_id
    if league_id:
        params["league"] = league_id
    if season:
        params["season"] = season
    if bookmaker:
        params["bookmaker"] = bookmaker
    if bet:
        params["bet"] = bet
    return _get("odds", params).get("response", [])


def get_odds_live(fixture_id: Optional[int] = None,
                  league_id: Optional[int] = None,
                  bet: Optional[int] = None) -> list[dict]:
    """Get live/in-play odds."""
    params: dict[str, Any] = {}
    if fixture_id:
        params["fixture"] = fixture_id
    if league_id:
        params["league"] = league_id
    if bet:
        params["bet"] = bet
    return _get("odds/live", params).get("response", [])


def get_odds_mapping(page: int = 1) -> dict:
    """Get mapping of fixtures to available odds. Updated daily."""
    return _get("odds/mapping", {"page": page}).get("response", {})


def get_odds_bookmakers() -> list[dict]:
    """List all available bookmakers."""
    return _get("odds/bookmakers", {}).get("response", [])


def get_odds_bets() -> list[dict]:
    """List all available bet types with IDs."""
    return _get("odds/bets", {}).get("response", [])


def get_predictions(fixture_id: int) -> list[dict]:
    """Get API predictions for a fixture (win/draw/loss %, goals, etc.)."""
    return _get("predictions", {"fixture": fixture_id}).get("response", [])


def get_teams(team_id: Optional[int] = None,
              league_id: Optional[int] = None,
              season: Optional[int] = None,
              name: Optional[str] = None,
              country: Optional[str] = None) -> list[dict]:
    """Get team information. Filter by ID, league, name, or country."""
    params: dict[str, Any] = {}
    if team_id:
        params["id"] = team_id
    if league_id:
        params["league"] = league_id
    if season:
        params["season"] = season
    if name:
        params["name"] = name
    if country:
        params["country"] = country
    return _get("teams", params).get("response", [])


def get_team_statistics(team_id: int, league_id: int, season: int) -> dict:
    """Get team statistics for a specific league season. Returns a dict with
    'response' containing team stats (form, goals, cards, etc.)."""
    params = {"team": team_id, "league": league_id, "season": season}
    return _get("teams/statistics", params)


def get_players(team_id: Optional[int] = None,
                league_id: Optional[int] = None,
                season: Optional[int] = None,
                search: Optional[str] = None,
                page: int = 1) -> list[dict]:
    """Get player information. Filter by team, league, season, or search by name."""
    params: dict[str, Any] = {"page": page}
    if team_id:
        params["team"] = team_id
    if league_id:
        params["league"] = league_id
    if season:
        params["season"] = season
    if search:
        params["search"] = search
    return _get("players", params).get("response", [])


def get_players_squads(team_id: int) -> list[dict]:
    """Get current squad for a team."""
    return _get("players/squads", {"team": team_id}).get("response", [])


def get_standings(league_id: int, season: int, 
                  team_id: Optional[int] = None) -> list[dict]:
    """Get league standings."""
    params: dict[str, Any] = {"league": league_id, "season": season}
    if team_id:
        params["team"] = team_id
    return _get("standings", params).get("response", [])


def get_leagues(team_id: Optional[int] = None,
                country: Optional[str] = None,
                season: Optional[int] = None,
                league_id: Optional[int] = None,
                search: Optional[str] = None) -> list[dict]:
    """Search leagues/competitions."""
    params: dict[str, Any] = {}
    if team_id:
        params["team"] = team_id
    if country:
        params["country"] = country
    if season:
        params["season"] = season
    if league_id:
        params["id"] = league_id
    if search:
        params["search"] = search
    return _get("leagues", params).get("response", [])


def get_injuries(team_id: Optional[int] = None,
                 league_id: Optional[int] = None,
                 season: Optional[int] = None,
                 fixture_id: Optional[int] = None,
                 player_id: Optional[int] = None) -> list[dict]:
    """Get injury/suspension information."""
    params: dict[str, Any] = {}
    if team_id:
        params["team"] = team_id
    if league_id:
        params["league"] = league_id
    if season:
        params["season"] = season
    if fixture_id:
        params["fixture"] = fixture_id
    if player_id:
        params["player"] = player_id
    return _get("injuries", params).get("response", [])


def get_transfers(player_id: Optional[int] = None,
                  team_id: Optional[int] = None) -> list[dict]:
    """Get transfer history."""
    params: dict[str, Any] = {}
    if player_id:
        params["player"] = player_id
    if team_id:
        params["team"] = team_id
    return _get("transfers", params).get("response", [])


# --- Bet type ID constants ---
BET_MATCH_WINNER = 1
BET_ASIAN_HANDICAP = 2
BET_GOALS_OVER_UNDER = 5
BET_GOALS_OU_FIRST_HALF = 6
BET_BOTH_TEAMS_SCORE = 8
BET_DOUBLE_CHANCE = 12
BET_CORRECT_SCORE = 45
BET_HTFT_RESULT = 46
BET_HOME_AWAY = 50

# --- Bookmaker ID constants (most commonly useful ones) ---
BOOKMAKER_PINNACLE = 8
BOOKMAKER_BET365 = 9
BOOKMAKER_WILLIAM_HILL = 2
BOOKMAKER_BWIN = 4
BOOKMAKER_1XBET = 24
BOOKMAKER_BETFAIR = 3
BOOKMAKER_MARATHONBET = 15
BOOKMAKER_UNIBET = 26
