"""The Odds API v4 client — odds data from 40+ bookmakers.

Requires ODDS_API_KEY environment variable.
Free tier: 500 credits/month.

Register at: https://the-odds-api.com/#get-access
"""

import os
import requests
from typing import Any, Optional

from utils import RateLimitError

BASE_URL = "https://api.the-odds-api.com/v4"
DEFAULT_REGIONS = "us,uk,eu"
DEFAULT_MARKETS = "h2h,spreads,totals"

# Map football-data.org competition codes → The Odds API sport keys
COMP_TO_SPORT = {
    "PL": "soccer_epl",
    "PD": "soccer_spain_la_liga",
    "BL1": "soccer_germany_bundesliga",
    "SA": "soccer_italy_serie_a",
    "FL1": "soccer_france_ligue_one",
    "CL": "soccer_uefa_champs_league",
    "EL": "soccer_uefa_europa_league", 
    "EC": "soccer_uefa_european_championship",
    "DED": "soccer_netherlands_eredivisie",
    "PPL": "soccer_portugal_primeira_liga",
    "BSA": "soccer_brazil_campeonato",
    "WC": "soccer_uefa_european_championship",  # fallback
}

# Legacy mapping (API-Football league IDs — kept for backwards compat)
_LEAGUE_ID_TO_SPORT_LEGACY = {
    39: "soccer_epl",
    140: "soccer_spain_la_liga",
    78: "soccer_germany_bundesliga",
    135: "soccer_italy_serie_a",
    61: "soccer_france_ligue_one",
    2: "soccer_uefa_champs_league",
    3: "soccer_uefa_europa_league",
    4: "soccer_uefa_european_championship",
    98: "soccer_japan_j_league",
    71: "soccer_brazil_campeonato",
    88: "soccer_netherlands_eredivisie",
    94: "soccer_portugal_primeira_liga",
    253: "soccer_usa_mls",
}


def _api_key() -> str:
    key = os.environ.get("ODDS_API_KEY", "")
    if not key:
        raise RuntimeError("ODDS_API_KEY environment variable not set. Register at https://the-odds-api.com/")
    return key


def _get(endpoint: str, params: Optional[dict[str, Any]] = None) -> dict:
    url = f"{BASE_URL}/{endpoint}"
    all_params = {"apiKey": _api_key()}
    if params:
        all_params.update(params)
    
    resp = requests.get(url, params=all_params, timeout=30)
    
    if resp.status_code == 429:
        raise RateLimitError("Odds API rate limit reached. Upgrade plan for more credits.")
    if resp.status_code == 401:
        raise RuntimeError("Invalid ODDS_API_KEY")
    if resp.status_code == 422:
        body = resp.json()
        raise RuntimeError(f"Odds API error: {body.get('message', resp.text[:200])}")
    if resp.status_code != 200:
        body = resp.text[:300]
        raise RuntimeError(f"Odds API returned {resp.status_code}: {body}")
    
    data = resp.json()
    
    # Log quota info
    remaining = resp.headers.get("x-requests-remaining", "?")
    used = resp.headers.get("x-requests-used", "?")
    
    return {
        "data": data,
        "quota_remaining": int(remaining) if remaining.isdigit() else remaining,
        "quota_used": int(used) if used.isdigit() else used,
    }


def get_sports() -> list[dict]:
    """List all in-season sports. Free — no quota cost."""
    return _get("sports").get("data", [])


def get_events(sport_key: str) -> list[dict]:
    """List events for a sport. Free — no quota cost."""
    return _get(f"sports/{sport_key}/events").get("data", [])


def get_odds(sport_key: str, regions: str = DEFAULT_REGIONS, 
             markets: str = DEFAULT_MARKETS,
             event_ids: Optional[str] = None) -> list[dict]:
    """Get odds for a sport. Cost = len(regions) × len(markets) credits."""
    params: dict[str, Any] = {
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
    }
    if event_ids:
        params["eventIds"] = event_ids
    result = _get(f"sports/{sport_key}/odds", params)
    return result.get("data", [])


def get_event_odds(sport_key: str, event_id: str,
                   regions: str = DEFAULT_REGIONS,
                   markets: str = DEFAULT_MARKETS) -> list[dict]:
    """Get odds for a single event."""
    params = {
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
    }
    result = _get(f"sports/{sport_key}/events/{event_id}/odds", params)
    return result.get("data", [])


def get_scores(sport_key: str, days_from: int = 3) -> list[dict]:
    """Get scores. Cost: 2 credits (with daysFrom)."""
    result = _get(f"sports/{sport_key}/scores", {"daysFrom": days_from})
    return result.get("data", [])


def get_historical_odds(sport_key: str, date: str,
                        regions: str = "us,uk,eu",
                        markets: str = "h2h") -> list[dict]:
    """Get historical odds snapshot for a date. 
    Cost = len(regions) × len(markets) credits.
    date format: ISO 8601, e.g. '2024-01-01T00:00:00Z'
    """
    params = {
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
        "date": date,
    }
    result = _get(f"sports/{sport_key}/odds-history", params)
    return result.get("data", {})


def get_sport_key(league_id: Any) -> Optional[str]:
    """Map competition ID (football-data.org string or API-Football int) to The Odds API sport key."""
    if isinstance(league_id, str):
        return COMP_TO_SPORT.get(league_id)
    return _LEAGUE_ID_TO_SPORT_LEGACY.get(league_id)


def extract_h2h_odds(odds_data: list[dict], home_team: str, away_team: str) -> dict:
    """Extract 1X2 odds from odds data for a specific match.
    Returns {bookmaker_name: {Home: odds, Draw: odds, Away: odds}, ...}
    """
    result = {}
    if not odds_data:
        return result
    
    # If odds_data is from get_odds (list of matches), find the right match
    # If from get_event_odds, it might just be the match data directly
    matches = odds_data
    if isinstance(odds_data, dict) and "bookmakers" in odds_data:
        matches = [odds_data]
    
    for match in matches:
        if match.get("home_team") == home_team and match.get("away_team") == away_team:
            for bm in match.get("bookmakers", []):
                bm_name = bm.get("title", bm.get("key", "Unknown"))
                for market in bm.get("markets", []):
                    if market.get("key") == "h2h":
                        for outcome in market.get("outcomes", []):
                            result.setdefault(bm_name, {})[outcome["name"]] = outcome["price"]
            return result
    
    return result


def extract_spreads(odds_data: list[dict], home_team: str, away_team: str) -> dict:
    """Extract Asian handicap / spread odds.
    Returns {bookmaker_name: {team_name: {price, point}, ...}, ...}
    """
    result = {}
    if not odds_data:
        return result
    
    for match in odds_data:
        if match.get("home_team") == home_team and match.get("away_team") == away_team:
            for bm in match.get("bookmakers", []):
                bm_name = bm.get("title", bm.get("key", "Unknown"))
                for market in bm.get("markets", []):
                    if market.get("key") == "spreads":
                        for outcome in market.get("outcomes", []):
                            result.setdefault(bm_name, {})[outcome["name"]] = {
                                "price": outcome["price"],
                                "point": outcome.get("point", 0),
                            }
            return result
    
    return result


def extract_totals(odds_data: list[dict], home_team: str, away_team: str) -> dict:
    """Extract over/under totals odds.
    Returns {bookmaker_name: {Over/Under: {price, point}, ...}, ...}
    """
    result = {}
    if not odds_data:
        return result
    
    for match in odds_data:
        if match.get("home_team") == home_team and match.get("away_team") == away_team:
            for bm in match.get("bookmakers", []):
                bm_name = bm.get("title", bm.get("key", "Unknown"))
                for market in bm.get("markets", []):
                    if market.get("key") == "totals":
                        for outcome in market.get("outcomes", []):
                            result.setdefault(bm_name, {})[outcome["name"]] = {
                                "price": outcome["price"],
                                "point": outcome.get("point", 0),
                            }
            return result
    
    return result
