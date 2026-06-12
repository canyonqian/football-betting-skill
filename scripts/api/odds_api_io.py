"""Odds-API.io client — odds data from 265+ bookmakers including Bet365.

Requires ODDS_API_IO_KEY environment variable.
Free tier: 2 bookmakers, 100 requests/hour.

Register at: https://odds-api.io
"""

import os
import requests
from typing import Any, Optional

BASE_URL = "https://api.odds-api.io/v3"


def _api_key() -> str:
    key = os.environ.get("ODDS_API_IO_KEY", "")
    if not key:
        raise RuntimeError("ODDS_API_IO_KEY not set. Register at https://odds-api.io")
    return key


GET_TIMEOUT = 20


def get_sports() -> list[dict]:
    """List all available sports (no auth needed)."""
    resp = requests.get(f"{BASE_URL}/sports", timeout=GET_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"odds-api.io sports endpoint: {resp.status_code}")
    return resp.json()


def get_leagues(sport: str = "football") -> list[dict]:
    """List leagues for a sport."""
    resp = requests.get(
        f"{BASE_URL}/leagues",
        params={"apiKey": _api_key(), "sport": sport},
        timeout=GET_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"odds-api.io leagues: {resp.status_code} {resp.text[:200]}")
    return resp.json()


def get_events(
    sport: str = "football",
    league: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 30,
) -> list[dict]:
    """Get upcoming or live events for a sport/league.

    Args:
        sport: sport slug (e.g. "football")
        league: league slug (e.g. "international-fifa-world-cup")
        status: "live" or None for upcoming
        limit: max events to return
    """
    params: dict[str, Any] = {"apiKey": _api_key(), "sport": sport, "limit": limit}
    if league:
        params["league"] = league
    if status:
        params["status"] = status
    resp = requests.get(f"{BASE_URL}/events", params=params, timeout=GET_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"odds-api.io events: {resp.status_code} {resp.text[:200]}")
    return resp.json()


def get_odds(
    event_id: int,
    bookmakers: str = "Bet365,Unibet",
) -> dict:
    """Get odds from selected bookmakers for a single event.

    Args:
        event_id: The event ID from get_events().
        bookmakers: Comma-separated bookmaker slugs.

    Returns:
        {
            "id": ...,
            "home": "...", "away": "...",
            "bookmakers": {
                "Bet365": [
                    {"name": "ML", "odds": [{"home": "1.57", "draw": "4.00", "away": "6.00"}], "updatedAt": "..."},
                    {"name": "Spread", "odds": [{"hdp": -0.5, "home": "1.825", "away": "2.025"}]},
                    ...
                ],
                ...
            }
        }
    """
    resp = requests.get(
        f"{BASE_URL}/odds",
        params={"apiKey": _api_key(), "eventId": event_id, "bookmakers": bookmakers},
        timeout=GET_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"odds-api.io odds: {resp.status_code} {resp.text[:200]}")
    return resp.json()


def find_event_id(home_team: str, away_team: str, league: str = "international-fifa-world-cup") -> Optional[int]:
    """Find event ID by team names."""
    events = get_events(league=league)
    for e in events:
        h = e.get("home", "").lower()
        a = e.get("away", "").lower()
        if home_team.lower() in h and away_team.lower() in a:
            return e.get("id")
        if away_team.lower() in h and home_team.lower() in a:
            return e.get("id")
    return None


def extract_odds_summary(odds_data: dict) -> dict:
    """Extract a summary of key markets from odds-api.io response.

    Returns {bookmaker: {market_name: {odds_field: value, ...}, ...}, ...}
    """
    result = {}
    for book_name, markets in odds_data.get("bookmakers", {}).items():
        result[book_name] = {}
        for market in markets:
            mname = market.get("name")
            odds_list = market.get("odds", [])
            if mname and odds_list:
                result[book_name][mname] = odds_list
    return result
