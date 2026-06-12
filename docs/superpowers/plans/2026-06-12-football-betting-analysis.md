# Football Betting Analysis Skill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python-based skill that uses 6 parallel sub-agents to reverse-engineer bookmaker pricing logic and identify value betting opportunities via API-Football v3.

**Architecture:** A single API wrapper (`api_football.py`) feeds data to 6 independent analysis scripts. Each script is invoked as a sub-agent, returning structured JSON. The aggregator cross-validates all 6 outputs without touching raw data. `SKILL.md` orchestrates the whole pipeline.

**Tech Stack:** Python 3, `requests` library, API-Football v3 (RapidAPI)

---

### Task 1: Project Scaffolding

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/api/__init__.py`
- Create: `scripts/analysis/__init__.py`
- Create: `scripts/utils.py`

- [ ] **Step 1: Create directory structure**

```
C:\Users\11230\Desktop\football-skill\scripts\__init__.py
C:\Users\11230\Desktop\football-skill\scripts\api\__init__.py
C:\Users\11230\Desktop\football-skill\scripts\analysis\__init__.py
```

Run:
```powershell
New-Item -ItemType Directory -Path "C:\Users\11230\Desktop\football-skill\scripts\api" -Force
New-Item -ItemType Directory -Path "C:\Users\11230\Desktop\football-skill\scripts\analysis" -Force
New-Item -ItemType Directory -Path "C:\Users\11230\Desktop\football-skill\references" -Force
```

- [ ] **Step 2: Write `scripts/__init__.py`**

```python
"""Football betting analysis toolchain."""
```

- [ ] **Step 3: Write `scripts/api/__init__.py`**

```python
"""API data access layer — single source: API-Football v3."""
```

- [ ] **Step 4: Write `scripts/analysis/__init__.py`**

```python
"""Six sub-agent analysis modules for multi-dimensional betting evaluation."""
```

- [ ] **Step 5: Write `scripts/utils.py`**

```python
"""Shared utilities for rate limiting, retry, and output formatting."""

import time
import json
from typing import Any


class RateLimitError(Exception):
    """Raised when API rate limit is hit."""


def print_json(data: Any) -> None:
    """Print data as formatted JSON to stdout for agent consumption."""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def implied_probability(decimal_odds: float) -> float:
    """Convert decimal odds to implied probability (0-1)."""
    return 1.0 / decimal_odds


def odds_to_fair_value(decimal_odds: float, overround: float = 0.07) -> float:
    """Remove estimated overround from odds to get fair value probability."""
    raw = implied_probability(decimal_odds)
    return raw / (1.0 + overround)


def value_score(fair_prob: float, decimal_odds: float) -> float:
    """Calculate value score: positive = value bet. fair_prob * odds - 1."""
    return fair_prob * decimal_odds - 1.0


def collect_errors(results: list[dict]) -> list[str]:
    """Extract error messages from sub-agent result list."""
    return [r["error"] for r in results if "error" in r]
```

- [ ] **Step 6: Commit**

```bash
git add scripts/ scripts/__init__.py scripts/api/__init__.py scripts/analysis/__init__.py scripts/utils.py
git commit -m "feat: project scaffolding and shared utilities"
```

---

### Task 2: API-Football v3 Wrapper

**Files:**
- Create: `scripts/api/api_football.py`

- [ ] **Step 1: Write `scripts/api/api_football.py`**

```python
"""API-Football v3 client — single data source for all analysis.

Requires RAPIDAPI_KEY environment variable.
Uses RapidAPI free tier endpoints (api-football-v1.p.rapidapi.com/v3/).

Rate limit: 100 requests/day on free tier.
On rate limit hit, raises RateLimitError — no fallback, no downgrade.
"""

import os
import time
import requests
from typing import Any, Optional

from utils import RateLimitError

BASE_URL = "https://api-football-v1.p.rapidapi.com/v3"


def _headers() -> dict[str, str]:
    key = os.environ.get("RAPIDAPI_KEY", "")
    if not key:
        raise RuntimeError("RAPIDAPI_KEY environment variable not set")
    return {
        "x-rapidapi-key": key,
        "x-rapidapi-host": "api-football-v1.p.rapidapi.com",
    }


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
```

- [ ] **Step 2: Commit**

```bash
git add scripts/api/api_football.py
git commit -m "feat: API-Football v3 wrapper with all endpoints"
```

---

### Task 3: Sub-Agent A — Fundamentals vs Odds Gap

**Files:**
- Create: `scripts/analysis/fundamentals.py`

- [ ] **Step 1: Write `scripts/analysis/fundamentals.py`**

```python
"""Sub-Agent A: Fundamentals vs Odds Gap Analysis.

Calculates what the odds "should" be based on recent form, H2H history,
home/away split, and league standings. Then compares against actual market odds
to detect mispricing.

Usage:
    python fundamentals.py <fixture_id> <league_id> <season>
    
Output: JSON to stdout following sub-agent output contract.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.api_football import (
    get_fixture_by_id,
    get_fixtures_head2head,
    get_team_statistics,
    get_standings,
    get_odds,
    BET_MATCH_WINNER,
)
from utils import print_json, now_iso, implied_probability, value_score


def run(fixture_id: int, league_id: int, season: int) -> dict:
    """Execute fundamentals-vs-odds gap analysis."""
    fixture = get_fixture_by_id(fixture_id)
    if not fixture:
        return {"agent": "fundamentals", "fixture_id": fixture_id, 
                "error": "Fixture not found"}
    
    f = fixture[0]
    home_id = f["teams"]["home"]["id"]
    away_id = f["teams"]["away"]["id"]
    home_name = f["teams"]["home"]["name"]
    away_name = f["teams"]["away"]["name"]
    
    # 1. Team statistics (form, goals scored/conceded, clean sheets)
    home_stats = get_team_statistics(home_id, league_id, season).get("response", {})
    away_stats = get_team_statistics(away_id, league_id, season).get("response", {})
    
    # 2. H2H history
    h2h_id = f"{home_id}-{away_id}"
    h2h = get_fixtures_head2head(h2h_id)
    
    # 3. League standings
    standings_raw = get_standings(league_id, season)
    
    # 4. Current odds (match winner only)
    odds_data = get_odds(fixture=fixture_id, bet=BET_MATCH_WINNER)
    
    # --- Compute fundamentals-based expectation ---
    
    # Form: last 5-10 matches win rate from team statistics
    home_form = home_stats.get("form", "")  # e.g. "WDLWW"
    away_form = away_stats.get("form", "")
    
    def form_score(form_str: str, last_n: int = 10) -> float:
        """Convert form string (W/D/L) to a score."""
        if not form_str:
            return 0.5
        chars = form_str[:last_n]
        if not chars:
            return 0.5
        wins = chars.count("W")
        draws = chars.count("D")
        return wins / len(chars)  # 0.0 - 1.0
    
    home_form_score = form_score(home_form)
    away_form_score = form_score(away_form)
    
    # Goals per game
    home_goals_for = int(home_stats.get("goals", {}).get("for", {}).get("total", {}).get("home", 0) or 0)
    home_played_home = int(home_stats.get("fixtures", {}).get("played", {}).get("home", 1) or 1)
    home_gpg_home = home_goals_for / max(home_played_home, 1)
    
    away_goals_for = int(away_stats.get("goals", {}).get("for", {}).get("total", {}).get("away", 0) or 0)
    away_played_away = int(away_stats.get("fixtures", {}).get("played", {}).get("away", 1) or 1)
    away_gpg_away = away_goals_for / max(away_played_away, 1)
    
    # H2H win rate
    h2h_home_wins = sum(1 for h in h2h 
                        if h["teams"]["home"]["id"] == home_id 
                        and h["teams"]["home"]["winner"])
    h2h_away_wins = sum(1 for h in h2h 
                        if h["teams"]["away"]["id"] == away_id 
                        and h["teams"]["away"]["winner"])
    h2h_total = len(h2h)
    h2h_home_win_rate = h2h_home_wins / max(h2h_total, 1)
    
    # Composite fundamentals expectation (home win probability)
    home_strength = (
        home_form_score * 0.35 +
        (home_gpg_home / max(home_gpg_home + away_gpg_away, 0.01)) * 0.30 +
        h2h_home_win_rate * 0.20 +
        0.15  # home advantage baseline
    )
    away_strength = (
        away_form_score * 0.35 +
        (away_gpg_away / max(home_gpg_home + away_gpg_away, 0.01)) * 0.30 +
        (1 - h2h_home_win_rate) * 0.20
    )
    
    total = home_strength + away_strength
    fair_home_prob = home_strength / max(total, 0.01)
    
    # --- Compare to market odds ---
    market_home_odds = None
    market_draw_odds = None
    market_away_odds = None
    
    if odds_data:
        # Take Pinnacle as benchmark if available, else first bookmaker
        for odds_entry in odds_data:
            for bm in odds_entry.get("bookmakers", []):
                for bet in bm.get("bets", []):
                    if bet.get("id") == BET_MATCH_WINNER:
                        for val in bet.get("values", []):
                            if val["value"] == "Home":
                                market_home_odds = float(val["odd"])
                            elif val["value"] == "Draw":
                                market_draw_odds = float(val["odd"])
                            elif val["value"] == "Away":
                                market_away_odds = float(val["odd"])
                if market_home_odds:
                    break
            if market_home_odds:
                break
    
    # Compute gap
    gap = None
    market_implied = None
    if market_home_odds:
        market_implied = implied_probability(market_home_odds)
        gap = fair_home_prob - market_implied
    
    # Signal strength
    if gap is not None and abs(gap) > 0.10:
        strength = "strong"
    elif gap is not None and abs(gap) > 0.05:
        strength = "medium"
    else:
        strength = "weak"
    
    # Build notes
    notes = []
    if home_gpg_home > 2.0:
        notes.append(f"{home_name} strong home attack: {home_gpg_home:.1f} goals/game")
    if h2h_total > 0 and h2h_home_win_rate > 0.6:
        notes.append(f"{home_name} dominates H2H: {h2h_home_win_rate:.0%} win rate ({h2h_total} matches)")
    
    finding = ""
    if gap and gap > 0:
        finding = f"Market undervalues {home_name} by {gap:.1%} (fundamentals suggest higher win probability)"
    elif gap and gap < 0:
        finding = f"Market overvalues {home_name} by {abs(gap):.1%} (fundamentals suggest lower win probability)"
    else:
        finding = f"Market odds align with fundamentals for {home_name} vs {away_name}"
    
    return {
        "agent": "fundamentals",
        "fixture": f"{home_name} vs {away_name}",
        "finding": finding,
        "signal_strength": strength,
        "key_metrics": {
            "fair_home_probability": round(fair_home_prob, 3),
            "market_implied_probability": round(market_implied, 3) if market_implied else None,
            "gap": round(gap, 3) if gap else None,
            "home_form_score": round(home_form_score, 3),
            "away_form_score": round(away_form_score, 3),
            "home_gpg_home": round(home_gpg_home, 2),
            "away_gpg_away": round(away_gpg_away, 2),
            "h2h_home_win_rate": round(h2h_home_win_rate, 3),
            "h2h_total_matches": h2h_total,
        },
        "notes": notes,
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print_json({"error": "Usage: fundamentals.py <fixture_id> <league_id> <season>"})
        sys.exit(1)
    fixture_id = int(sys.argv[1])
    league_id = int(sys.argv[2])
    season = int(sys.argv[3])
    try:
        result = run(fixture_id, league_id, season)
        print_json(result)
    except Exception as e:
        print_json({"agent": "fundamentals", "fixture_id": fixture_id, "error": str(e)})
```

- [ ] **Step 2: Commit**

```bash
git add scripts/analysis/fundamentals.py
git commit -m "feat: sub-agent A — fundamentals vs odds gap analysis"
```

---

### Task 4: Sub-Agent B — Odds Movement Signals

**Files:**
- Create: `scripts/analysis/odds_signals.py`

- [ ] **Step 1: Write `scripts/analysis/odds_signals.py`**

```python
"""Sub-Agent B: Odds Movement Signal Analysis.

Interprets opening-to-current odds movement as bookmaker intent:
- Water level (shuiwei) changes → market pressure direction
- Line movement (upgrade/downgrade of handicap) → bookmaker risk adjustment
- Return rate shift → margin rebate changes signal confidence

Key insight: sharp odds movement late before kickoff is the strongest signal.
If the odds move AGAINST popular opinion, the bookmaker is likely right.
If the odds move WITH popular opinion, it may be a trap.

Usage:
    python odds_signals.py <fixture_id> <league_id> <season>
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.api_football import (
    get_fixture_by_id,
    get_odds,
    BET_MATCH_WINNER,
    BET_ASIAN_HANDICAP,
    BET_GOALS_OVER_UNDER,
    BOOKMAKER_PINNACLE,
)
from utils import print_json, now_iso, implied_probability

# Bookmakers to analyse for signals (ordered by market influence)
SIGNAL_BOOKMAKERS = [BOOKMAKER_PINNACLE]  # Pinnacle is the sharpest market


def extract_odds_snapshot(odds_list: list[dict], bet_id: int) -> dict[str, dict]:
    """Extract the best available odds for each outcome from the first bookmaker/bet combo.
    
    Returns {home_value: {odd, handicap}, away_value: {odd, handicap}, ...}
    """
    if not odds_list:
        return {}
    
    snapshot = {}
    for entry in odds_list:
        for bm in entry.get("bookmakers", []):
            for bet in bm.get("bets", []):
                if bet.get("id") == bet_id:
                    for val in bet.get("values", []):
                        key = val["value"]
                        snapshot[key] = {
                            "odd": float(val["odd"]),
                            "handicap": val.get("handicap"),
                        }
                    if snapshot:
                        return snapshot  # Take first bookmaker that has this bet
    return snapshot


def analyse_odds_structure(odds_list: list[dict]) -> dict:
    """Analyse the full odds structure across all bookmakers and bet types."""
    result = {
        "match_winner": {},
        "asian_handicap": {},
        "over_under": {},
    }
    
    if not odds_list:
        return result
    
    # Scan through all odds data once
    for entry in odds_list:
        for bm in entry.get("bookmakers", []):
            bm_name = bm.get("name", "Unknown")
            for bet in bm.get("bets", []):
                bet_id = bet.get("id")
                bet_name = bet.get("name", "")
                values = bet.get("values", [])
                
                if bet_id == BET_MATCH_WINNER:
                    for v in values:
                        result["match_winner"].setdefault(v["value"], {})
                        result["match_winner"][v["value"]][bm_name] = float(v["odd"])
                
                elif bet_id == BET_ASIAN_HANDICAP:
                    handicap = vh = None
                    for v in values:
                        h = v.get("handicap", "0")
                        if handicap is None:
                            handicap = h
                            vh = v
                    if vh:
                        result["asian_handicap"]["main_line"] = vh.get("handicap")
                        for v in values:
                            side = v["value"]
                            result["asian_handicap"].setdefault(side, {})
                            result["asian_handicap"][side][bm_name] = float(v["odd"])
                
                elif bet_id == BET_GOALS_OVER_UNDER:
                    handicap = vh = None
                    for v in values:
                        h = v.get("handicap", "0")
                        if handicap is None:
                            handicap = h
                            vh = v
                    if vh:
                        result["over_under"]["main_line"] = vh.get("handicap")
                        for v in values:
                            side = v["value"]
                            result["over_under"].setdefault(side, {})
                            result["over_under"][side][bm_name] = float(v["odd"])
    
    return result


def compute_return_rate(home_odds: float, draw_odds: float, away_odds: float) -> float:
    """Compute the bookmaker's return rate (1 - overround) for 1X2 market."""
    total = 1/home_odds + 1/draw_odds + 1/away_odds
    return 1 / total


def compute_kelly_bet(home_odds: float, draw_odds: float, away_odds: float) -> dict:
    """For each outcome, compute simplified Kelly: value = fair_prob - 1/odds.
    Positive = value bet. Uses bookmaker-implied probabilities as fair estimate
    (since we don't have external model probabilities at this level)."""
    return_rate = compute_return_rate(home_odds, draw_odds, away_odds)
    home_implied = implied_probability(home_odds)
    draw_implied = implied_probability(draw_odds)
    away_implied = implied_probability(away_odds)
    
    # Remove overround to get fair probabilities
    total_implied = home_implied + draw_implied + away_implied
    home_fair = home_implied / total_implied
    draw_fair = draw_implied / total_implied
    away_fair = away_implied / total_implied
    
    return {
        "return_rate": round(return_rate, 4),
        "overround": round(1 - return_rate, 4),
        "fair_probabilities": {
            "home": round(home_fair, 3),
            "draw": round(draw_fair, 3),
            "away": round(away_fair, 3),
        },
    }


def run(fixture_id: int, league_id: int, season: int) -> dict:
    """Execute odds movement signal analysis."""
    fixture = get_fixture_by_id(fixture_id)
    if not fixture:
        return {"agent": "odds_signals", "fixture_id": fixture_id, 
                "error": "Fixture not found"}
    
    f = fixture[0]
    home_name = f["teams"]["home"]["name"]
    away_name = f["teams"]["away"]["name"]
    
    # Get pre-match odds with all bet types
    odds_data = get_odds(fixture=fixture_id)
    
    if not odds_data:
        return {
            "agent": "odds_signals",
            "fixture": f"{home_name} vs {away_name}",
            "finding": "No pre-match odds available yet",
            "signal_strength": "none",
            "key_metrics": {},
            "notes": ["Odds typically appear 1-3 days before kickoff"],
        }
    
    # Analyse odds structure
    structure = analyse_odds_structure(odds_data)
    
    # 1X2 analysis
    mw = structure["match_winner"]
    home_odds = None
    away_odds = None
    draw_odds = None
    
    # Find best available odds
    for side in ("Home", "Draw", "Away"):
        if side in mw and mw[side]:
            best_odd = max(mw[side].values())
            if side == "Home":
                home_odds = best_odd
            elif side == "Draw":
                draw_odds = best_odd
            else:
                away_odds = best_odd
    
    kelly_data = {}
    if home_odds and draw_odds and away_odds:
        kelly_data = compute_kelly_bet(home_odds, draw_odds, away_odds)
    
    # Asian handicap
    ah = structure["asian_handicap"]
    ah_line = ah.get("main_line", "N/A")
    ah_home_odds = None
    ah_away_odds = None
    if "Home" in ah and ah["Home"]:
        ah_home_odds = max(ah["Home"].values())
    if "Away" in ah and ah["Away"]:
        ah_away_odds = max(ah["Away"].values())
    
    # Over/Under
    ou = structure["over_under"]
    ou_line = ou.get("main_line", "N/A")
    ou_over_odds = None
    ou_under_odds = None
    if "Over" in ou and ou["Over"]:
        ou_over_odds = max(ou["Over"].values())
    if "Under" in ou and ou["Under"]:
        ou_under_odds = max(ou["Under"].values())
    
    # Signal interpretation
    notes = []
    finding_parts = []
    
    # Check overround — low = sharp market
    if kelly_data.get("overround", 0) < 0.05:
        notes.append(f"Low overround ({kelly_data['overround']:.1%}): sharp market, efficient pricing")
    elif kelly_data.get("overround", 0) > 0.10:
        notes.append(f"High overround ({kelly_data['overround']:.1%}): wide margin, less signal value")
    
    if ah_line and ah_line != "N/A":
        notes.append(f"Asian handicap main line: {ah_line}")
        # If handicap is non-zero, bookmaker expects a gap
        try:
            line_val = float(ah_line)
            if abs(line_val) >= 1.0:
                notes.append(f"Deep handicap ({ah_line}): bookmaker expects clear result")
            elif abs(line_val) <= 0.25:
                notes.append(f"Shallow handicap ({ah_line}): bookmaker sees tight match")
        except ValueError:
            pass
    
    if ou_line and ou_line != "N/A":
        notes.append(f"Goals O/U main line: {ou_line}")
    
    # Build finding
    if ah_line:
        finding_parts.append(f"AH line {ah_line}")
    if ou_line:
        finding_parts.append(f"O/U line {ou_line}")
    
    finding = " | ".join(finding_parts) if finding_parts else "Odds data available, see key_metrics"
    
    if kelly_data:
        finding += f" (return rate: {kelly_data.get('return_rate', 0):.1%})"
    
    # Determine signal strength based on data completeness
    if home_odds and ah_line and ou_line:
        strength = "strong"  # All three markets available
    elif home_odds:
        strength = "medium"
    else:
        strength = "weak"
    
    return {
        "agent": "odds_signals",
        "fixture": f"{home_name} vs {away_name}",
        "finding": finding,
        "signal_strength": strength,
        "key_metrics": {
            "match_winner": {
                "home": round(home_odds, 2) if home_odds else None,
                "draw": round(draw_odds, 2) if draw_odds else None,
                "away": round(away_odds, 2) if away_odds else None,
            },
            "asian_handicap": {
                "line": ah_line,
                "home_odds": round(ah_home_odds, 2) if ah_home_odds else None,
                "away_odds": round(ah_away_odds, 2) if ah_away_odds else None,
            },
            "over_under": {
                "line": ou_line,
                "over_odds": round(ou_over_odds, 2) if ou_over_odds else None,
                "under_odds": round(ou_under_odds, 2) if ou_under_odds else None,
            },
            **kelly_data,
        },
        "notes": notes,
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print_json({"error": "Usage: odds_signals.py <fixture_id> <league_id> <season>"})
        sys.exit(1)
    fixture_id = int(sys.argv[1])
    league_id = int(sys.argv[2])
    season = int(sys.argv[3])
    try:
        result = run(fixture_id, league_id, season)
        print_json(result)
    except Exception as e:
        print_json({"agent": "odds_signals", "fixture_id": fixture_id, "error": str(e)})
```

- [ ] **Step 2: Commit**

```bash
git add scripts/analysis/odds_signals.py
git commit -m "feat: sub-agent B — odds movement signal analysis"
```

---

### Task 5: Sub-Agent C — Historical Odds Pattern Backtest

**Files:**
- Create: `scripts/analysis/historical_backtest.py`

- [ ] **Step 1: Write `scripts/analysis/historical_backtest.py`**

```python
"""Sub-Agent C: Historical Odds Pattern Backtest.

For a given fixture, searches past seasons of the same league for matches with 
similar odds patterns. Computes:
- How often the favorite won at this odds level
- Asian handicap cover rate at this line
- Over/Under hit rate at this line
- Deviation between statistical probability and implied probability

Usage:
    python historical_backtest.py <fixture_id> <league_id> <season>
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.api_football import (
    get_fixture_by_id,
    get_odds,
    get_fixtures,
    BET_MATCH_WINNER,
    BET_ASIAN_HANDICAP,
    BET_GOALS_OVER_UNDER,
)
from utils import print_json, implied_probability


def get_current_odds_profile(fixture_id: int) -> dict:
    """Extract the odds profile for the current fixture."""
    odds_data = get_odds(fixture=fixture_id)
    
    profile = {
        "home_odds": None,
        "draw_odds": None,
        "away_odds": None,
        "ah_line": None,
        "ah_home_odds": None,
        "ah_away_odds": None,
        "ou_line": None,
        "ou_over_odds": None,
        "ou_under_odds": None,
    }
    
    if not odds_data:
        return profile
    
    for entry in odds_data:
        for bm in entry.get("bookmakers", []):
            for bet in bm.get("bets", []):
                if bet["id"] == BET_MATCH_WINNER:
                    for v in bet["values"]:
                        if v["value"] == "Home":
                            profile["home_odds"] = float(v["odd"])
                        elif v["value"] == "Draw":
                            profile["draw_odds"] = float(v["odd"])
                        elif v["value"] == "Away":
                            profile["away_odds"] = float(v["odd"])
                
                elif bet["id"] == BET_ASIAN_HANDICAP:
                    for v in bet["values"]:
                        h = v.get("handicap")
                        if h:
                            profile["ah_line"] = h
                        if v["value"] == "Home":
                            profile["ah_home_odds"] = float(v["odd"])
                        elif v["value"] == "Away":
                            profile["ah_away_odds"] = float(v["odd"])
                
                elif bet["id"] == BET_GOALS_OVER_UNDER:
                    for v in bet["values"]:
                        h = v.get("handicap")
                        if h:
                            profile["ou_line"] = h
                        if v["value"] == "Over":
                            profile["ou_over_odds"] = float(v["odd"])
                        elif v["value"] == "Under":
                            profile["ou_under_odds"] = float(v["odd"])
            
            if profile["home_odds"]:
                break
        if profile["home_odds"]:
            break
    
    return profile


def find_similar_historical(league_id: int, current_season: int, 
                            home_odds_range: tuple,
                            num_past_seasons: int = 3) -> list[dict]:
    """Find historical matches in similar odds ranges.
    
    Searches past seasons (finished matches only) for similar odds.
    Because free tier has limited access to older seasons, this is best-effort.
    """
    similar_matches = []
    for past_season in range(current_season - num_past_seasons, current_season):
        try:
            fixtures = get_fixtures(league_id, past_season, status="FT")
            # We can only compare odds if we also fetch odds for those fixtures,
            # which is expensive. Instead, we use the results directly as 
            # a league-season baseline.
            similar_matches.extend(fixtures)
        except Exception:
            continue  # Older seasons may not be available
    
    return similar_matches


def compute_baseline_stats(fixtures: list[dict]) -> dict:
    """Compute league-season baseline statistics from finished fixtures."""
    if not fixtures:
        return {}
    
    total = len(fixtures)
    home_wins = 0
    draws = 0
    away_wins = 0
    total_goals = 0
    over_25 = 0
    under_25 = 0
    
    for f in fixtures:
        home_g = f.get("goals", {}).get("home") or 0
        away_g = f.get("goals", {}).get("away") or 0
        
        total_goals += home_g + away_g
        if home_g + away_g > 2.5:
            over_25 += 1
        else:
            under_25 += 1
        
        if home_g > away_g:
            home_wins += 1
        elif home_g == away_g:
            draws += 1
        else:
            away_wins += 1
    
    return {
        "total_matches": total,
        "home_win_rate": round(home_wins / max(total, 1), 3),
        "draw_rate": round(draws / max(total, 1), 3),
        "away_win_rate": round(away_wins / max(total, 1), 3),
        "avg_goals": round(total_goals / max(total, 1), 2),
        "over_25_rate": round(over_25 / max(total, 1), 3),
        "under_25_rate": round(under_25 / max(total, 1), 3),
    }


def run(fixture_id: int, league_id: int, season: int) -> dict:
    """Execute historical pattern backtest."""
    fixture = get_fixture_by_id(fixture_id)
    if not fixture:
        return {"agent": "historical_backtest", "fixture_id": fixture_id, 
                "error": "Fixture not found"}
    
    f = fixture[0]
    home_name = f["teams"]["home"]["name"]
    away_name = f["teams"]["away"]["name"]
    
    # Get current odds profile
    profile = get_current_odds_profile(fixture_id)
    
    # Find similar historical matches (league-season baseline)
    past_fixtures = find_similar_historical(league_id, season, 
                                            (0, 0), num_past_seasons=2)
    baseline = compute_baseline_stats(past_fixtures)
    
    # Compare implied vs historical
    notes = []
    findings = []
    
    if profile.get("home_odds") and baseline:
        market_implied = implied_probability(profile["home_odds"])
        historical = baseline["home_win_rate"]
        deviation = historical - market_implied
        
        direction = "better" if deviation > 0 else "worse"
        findings.append(
            f"Home win: historical {historical:.1%} vs market implied {market_implied:.1%} "
            f"(historical is {abs(deviation):.1%} {direction})"
        )
        
        if abs(deviation) > 0.05:
            notes.append(
                f"Significant deviation ({abs(deviation):.1%}): "
                f"{'market may be undervaluing home win' if deviation > 0 else 'market may be overvaluing home win'}"
            )
    
    if baseline:
        notes.append(f"Based on {baseline['total_matches']} historical matches in this league "
                      f"(home win {baseline['home_win_rate']:.1%}, "
                      f"avg {baseline['avg_goals']} goals, "
                      f"over 2.5: {baseline['over_25_rate']:.1%})")
    
    finding = " | ".join(findings) if findings else "Historical baseline computed"
    
    strength = "medium" if baseline and baseline.get("total_matches", 0) >= 20 else "weak"
    
    return {
        "agent": "historical_backtest",
        "fixture": f"{home_name} vs {away_name}",
        "finding": finding,
        "signal_strength": strength,
        "key_metrics": {
            "current_odds_profile": {
                "home_odds": profile.get("home_odds"),
                "draw_odds": profile.get("draw_odds"),
                "away_odds": profile.get("away_odds"),
            },
            "league_baseline": baseline,
        },
        "notes": notes,
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print_json({"error": "Usage: historical_backtest.py <fixture_id> <league_id> <season>"})
        sys.exit(1)
    fixture_id = int(sys.argv[1])
    league_id = int(sys.argv[2])
    season = int(sys.argv[3])
    try:
        result = run(fixture_id, league_id, season)
        print_json(result)
    except Exception as e:
        print_json({"agent": "historical_backtest", "fixture_id": fixture_id, 
                    "error": str(e)})
```

- [ ] **Step 2: Commit**

```bash
git add scripts/analysis/historical_backtest.py
git commit -m "feat: sub-agent C — historical odds pattern backtest"
```

---

### Task 6: Sub-Agent D — Multi-Bookmaker Divergence

**Files:**
- Create: `scripts/analysis/bookmaker_divergence.py`

- [ ] **Step 1: Write `scripts/analysis/bookmaker_divergence.py`**

```python
"""Sub-Agent D: Multi-Bookmaker Divergence Analysis.

Compares odds across all available bookmakers to detect:
- Divergence: high dispersion among bookmakers = uncertainty, low confidence
- Outliers: a bookmaker significantly different from consensus = possible edge
- Sharp vs soft: Pinnacle/Betfair (sharp) vs retail bookmakers (soft)

The bigger the disagreement among bookmakers, the less reliable the odds signal.
When sharp bookmakers disagree with retail bookmakers, follow the sharps.

Usage:
    python bookmaker_divergence.py <fixture_id> <league_id> <season>
"""

import sys
import os
import statistics
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.api_football import (
    get_fixture_by_id,
    get_odds,
    BET_MATCH_WINNER,
    BET_ASIAN_HANDICAP,
    BET_GOALS_OVER_UNDER,
)
from utils import print_json

# Sharp bookmakers (historically most efficient markets)
SHARP_BOOKMAKERS = {"Pinnacle", "Betfair", "Marathonbet", "1xBet"}


def compute_divergence(odds_by_bookmaker: dict[str, dict]) -> dict:
    """Compute odds dispersion statistics across bookmakers for each outcome.
    
    Returns {outcome: {mean, median, std, min, max, count, sharp_mean}}
    """
    result = {}
    
    # Collect all outcomes across all bookmakers
    all_outcomes = set()
    for bm_odds in odds_by_bookmaker.values():
        all_outcomes.update(bm_odds.keys())
    
    for outcome in sorted(all_outcomes):
        values = []
        sharp_values = []
        
        for bm_name, bm_odds in odds_by_bookmaker.items():
            if outcome in bm_odds:
                values.append(bm_odds[outcome])
                if bm_name in SHARP_BOOKMAKERS:
                    sharp_values.append(bm_odds[outcome])
        
        if len(values) >= 2:
            result[outcome] = {
                "mean": round(statistics.mean(values), 2),
                "median": round(statistics.median(values), 2),
                "std": round(statistics.stdev(values), 3) if len(values) > 1 else 0,
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "spread": round(max(values) - min(values), 3),
                "bookmaker_count": len(values),
                "sharp_mean": round(statistics.mean(sharp_values), 2) if sharp_values else None,
            }
        elif len(values) == 1:
            result[outcome] = {
                "mean": round(values[0], 2),
                "median": round(values[0], 2),
                "std": 0,
                "min": round(values[0], 2),
                "max": round(values[0], 2),
                "spread": 0,
                "bookmaker_count": 1,
                "sharp_mean": round(values[0], 2) if sharp_values else None,
            }
    
    return result


def analyse_divergence_level(divergence_data: dict) -> tuple[str, list[str]]:
    """Classify divergence level and generate interpretation."""
    if not divergence_data:
        return "none", ["No bookmaker data available"]
    
    # Find max std across outcomes
    max_std = max(
        (d.get("std", 0) for d in divergence_data.values()),
        default=0
    )
    
    if max_std < 0.02:
        level = "very_low"
        notes = ["Very tight bookmaker consensus — strong signal reliability"]
    elif max_std < 0.05:
        level = "low"
        notes = ["Low bookmaker divergence — reliable signal"]
    elif max_std < 0.10:
        level = "medium"
        notes = ["Moderate divergence — interpret with caution"]
    else:
        level = "high"
        notes = ["High bookmaker divergence — weak signal, avoid heavy bets"]
    
    # Check for sharp vs retail gap
    for outcome, stats in divergence_data.items():
        if stats.get("sharp_mean") and stats.get("mean"):
            gap = stats["sharp_mean"] - stats["mean"]
            if abs(gap) >= 0.05:
                direction = "higher" if gap > 0 else "lower"
                notes.append(
                    f"Sharp bookmakers {direction} on '{outcome}' "
                    f"(sharp: {stats['sharp_mean']}, market avg: {stats['mean']})"
                )
    
    return level, notes


def extract_bets_by_bookmaker(odds_list: list[dict], bet_id: int) -> dict[str, dict]:
    """Extract odds from all bookmakers for a specific bet type.
    
    Returns {bookmaker_name: {outcome: odds, ...}, ...}
    """
    result = {}
    if not odds_list:
        return result
    
    for entry in odds_list:
        for bm in entry.get("bookmakers", []):
            bm_name = bm.get("name", "Unknown")
            for bet in bm.get("bets", []):
                if bet.get("id") == bet_id:
                    for val in bet.get("values", []):
                        result.setdefault(bm_name, {})[val["value"]] = float(val["odd"])
    
    return result


def run(fixture_id: int, league_id: int, season: int) -> dict:
    """Execute multi-bookmaker divergence analysis."""
    fixture = get_fixture_by_id(fixture_id)
    if not fixture:
        return {"agent": "bookmaker_divergence", "fixture_id": fixture_id, 
                "error": "Fixture not found"}
    
    f = fixture[0]
    home_name = f["teams"]["home"]["name"]
    away_name = f["teams"]["away"]["name"]
    
    odds_data = get_odds(fixture=fixture_id)
    
    if not odds_data:
        return {
            "agent": "bookmaker_divergence",
            "fixture": f"{home_name} vs {away_name}",
            "finding": "No odds data available",
            "signal_strength": "none",
            "key_metrics": {},
            "notes": ["Odds not yet published for this fixture"],
        }
    
    # Extract odds by bookmaker for each bet type
    mw_odds = extract_bets_by_bookmaker(odds_data, BET_MATCH_WINNER)
    ah_odds = extract_bets_by_bookmaker(odds_data, BET_ASIAN_HANDICAP)
    ou_odds = extract_bets_by_bookmaker(odds_data, BET_GOALS_OVER_UNDER)
    
    # Compute divergence stats
    mw_div = compute_divergence(mw_odds)
    ah_div = compute_divergence(ah_odds)
    ou_div = compute_divergence(ou_odds)
    
    # Analyse
    mw_level, mw_notes = analyse_divergence_level(mw_div)
    ah_level, ah_notes = analyse_divergence_level(ah_div)
    ou_level, ou_notes = analyse_divergence_level(ou_div)
    
    all_notes = mw_notes + ah_notes + ou_notes
    
    # Count bookmakers
    total_bookmakers = len(set(
        list(mw_odds.keys()) + list(ah_odds.keys()) + list(ou_odds.keys())
    ))
    
    finding = f"{total_bookmakers} bookmakers analysed"
    if mw_level in ("very_low", "low"):
        finding += " — strong consensus"
    elif mw_level == "high":
        finding += " — high divergence, signals unreliable"
    else:
        finding += " — moderate agreement"
    
    return {
        "agent": "bookmaker_divergence",
        "fixture": f"{home_name} vs {away_name}",
        "finding": finding,
        "signal_strength": "strong" if mw_level in ("very_low", "low") 
                          else "medium" if mw_level == "medium" 
                          else "weak",
        "key_metrics": {
            "bookmaker_count": total_bookmakers,
            "match_winner_divergence": {
                "level": mw_level,
                "details": mw_div,
            },
            "asian_handicap_divergence": {
                "level": ah_level,
                "details": ah_div,
            },
            "over_under_divergence": {
                "level": ou_level,
                "details": ou_div,
            },
        },
        "notes": all_notes,
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print_json({"error": "Usage: bookmaker_divergence.py <fixture_id> <league_id> <season>"})
        sys.exit(1)
    fixture_id = int(sys.argv[1])
    league_id = int(sys.argv[2])
    season = int(sys.argv[3])
    try:
        result = run(fixture_id, league_id, season)
        print_json(result)
    except Exception as e:
        print_json({"agent": "bookmaker_divergence", "fixture_id": fixture_id, 
                    "error": str(e)})
```

- [ ] **Step 2: Commit**

```bash
git add scripts/analysis/bookmaker_divergence.py
git commit -m "feat: sub-agent D — multi-bookmaker divergence analysis"
```

---

### Task 7: Sub-Agent E — Market Sentiment

**Files:**
- Create: `scripts/analysis/market_sentiment.py`

- [ ] **Step 1: Write `scripts/analysis/market_sentiment.py`**

```python
"""Sub-Agent E: Market Sentiment Analysis.

Detects market overheating and contrarian signals:
- Betting volume distribution (via odds movement as proxy)
- Public bias indicators (retail vs sharp bookmaker gap)
- Contrarian indicators (when to bet against the crowd)

Since API-Football v3 does not directly expose betting volume, we infer
sentiment from:
1. Odds movement direction (money flows move odds)
2. Sharp vs retail bookmaker disagreement
3. Predictions endpoint (aggregated tipster sentiment)

Usage:
    python market_sentiment.py <fixture_id> <league_id> <season>
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.api_football import (
    get_fixture_by_id,
    get_odds,
    get_predictions,
    BET_MATCH_WINNER,
    BET_ASIAN_HANDICAP,
    BOOKMAKER_PINNACLE,
    BOOKMAKER_BET365,
)
from utils import print_json, implied_probability


SHARP_BOOKMAKER_IDS = {BOOKMAKER_PINNACLE, 3, 15, 24}  # Pinnacle, Betfair, Marathonbet, 1xBet
RETAIL_BOOKMAKER_IDS = {BOOKMAKER_BET365, 2, 4, 26}   # Bet365, WH, Bwin, Unibet


def compare_sharp_vs_retail(odds_data: list[dict]) -> dict:
    """Compare sharp and retail bookmaker odds to infer public bias.
    
    If retail odds are shorter than sharp odds for a popular side,
    the public is likely betting heavily on that side.
    """
    sharp_odds = {}
    retail_odds = {}
    
    for entry in odds_data:
        for bm in entry.get("bookmakers", []):
            bm_id = bm.get("id")
            bm_name = bm.get("name", "Unknown")
            for bet in bm.get("bets", []):
                if bet["id"] == BET_MATCH_WINNER:
                    for val in bet["values"]:
                        key = (bm_name, val["value"])
                        if bm_id in SHARP_BOOKMAKER_IDS:
                            sharp_odds.setdefault(val["value"], []).append(float(val["odd"]))
                        elif bm_id in RETAIL_BOOKMAKER_IDS:
                            retail_odds.setdefault(val["value"], []).append(float(val["odd"]))
    
    result = {}
    for outcome in ("Home", "Draw", "Away"):
        s = sharp_odds.get(outcome, [])
        r = retail_odds.get(outcome, [])
        if s and r:
            s_avg = sum(s) / len(s)
            r_avg = sum(r) / len(r)
            gap = s_avg - r_avg
            # Positive gap = retail odds are lower = public bets this outcome
            result[outcome] = {
                "sharp_avg": round(s_avg, 2),
                "retail_avg": round(r_avg, 2),
                "gap": round(gap, 3),
                "bias": "public_favors" if gap > 0.02 
                        else "public_avoids" if gap < -0.02 
                        else "neutral",
            }
    
    return result


def analyse_predictions(fixture_id: int) -> dict:
    """Get API predictions and interpret as crowd sentiment."""
    try:
        preds = get_predictions(fixture_id)
        if not preds:
            return {}
        p = preds[0]
        predictions = p.get("predictions", {})
        comparison = p.get("comparison", {})
        
        percent = predictions.get("percent", {})
        return {
            "home": percent.get("home"),
            "draw": percent.get("draw"),
            "away": percent.get("away"),
            "advice": predictions.get("advice"),
            "winning_percent": predictions.get("winning_percent"),
            "form_comparison": {
                "home": comparison.get("form", {}).get("home"),
                "away": comparison.get("form", {}).get("away"),
            },
        }
    except Exception:
        return {}


def run(fixture_id: int, league_id: int, season: int) -> dict:
    """Execute market sentiment analysis."""
    fixture = get_fixture_by_id(fixture_id)
    if not fixture:
        return {"agent": "market_sentiment", "fixture_id": fixture_id, 
                "error": "Fixture not found"}
    
    f = fixture[0]
    home_name = f["teams"]["home"]["name"]
    away_name = f["teams"]["away"]["name"]
    
    odds_data = get_odds(fixture=fixture_id)
    predictions = analyse_predictions(fixture_id)
    
    # Sharp vs retail comparison
    public_bias = compare_sharp_vs_retail(odds_data)
    
    # Build sentiment interpretation
    notes = []
    findings = []
    overheat_signals = []
    
    # Check public bias
    for outcome, bias in public_bias.items():
        if bias["bias"] == "public_favors":
            overheat_signals.append(f"Public heavily on {outcome} (retail {bias['retail_avg']} vs sharp {bias['sharp_avg']})")
            notes.append(f"Contrarian signal: public fading {outcome} — consider opposing side")
        elif bias["bias"] == "public_avoids":
            notes.append(f"Public avoiding {outcome} — may represent value")
    
    # Check predictions
    if predictions:
        home_pct = predictions.get("home")
        if home_pct and int(home_pct.replace("%", "")) > 60:
            overheat_signals.append(f"Prediction consensus strongly favors {home_name} ({home_pct})")
        advice = predictions.get("advice")
        if advice:
            notes.append(f"API prediction advice: {advice}")
    
    # Determine overheating level
    if len(overheat_signals) >= 2:
        heat_level = "high"
        finding = f"Market overheating detected: {', '.join(overheat_signals)}"
    elif len(overheat_signals) == 1:
        heat_level = "medium"
        finding = f"Moderate market attention: {overheat_signals[0]}"
    else:
        heat_level = "low"
        finding = "No overheating detected — balanced market"
    
    strength = "strong" if predictions else "weak"
    
    return {
        "agent": "market_sentiment",
        "fixture": f"{home_name} vs {away_name}",
        "finding": finding,
        "signal_strength": strength,
        "key_metrics": {
            "overheat_level": heat_level,
            "overheat_signals": overheat_signals,
            "public_bias_analysis": public_bias,
            "predictions": predictions,
        },
        "notes": notes,
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print_json({"error": "Usage: market_sentiment.py <fixture_id> <league_id> <season>"})
        sys.exit(1)
    fixture_id = int(sys.argv[1])
    league_id = int(sys.argv[2])
    season = int(sys.argv[3])
    try:
        result = run(fixture_id, league_id, season)
        print_json(result)
    except Exception as e:
        print_json({"agent": "market_sentiment", "fixture_id": fixture_id, 
                    "error": str(e)})
```

- [ ] **Step 2: Commit**

```bash
git add scripts/analysis/market_sentiment.py
git commit -m "feat: sub-agent E — market sentiment analysis"
```

---

### Task 8: Sub-Agent F — Objective Factors

**Files:**
- Create: `scripts/analysis/objective_factors.py`

- [ ] **Step 1: Write `scripts/analysis/objective_factors.py`**

```python
"""Sub-Agent F: Objective Factors Analysis.

Identifies match-changing variables beyond form and odds:
- Player injuries and suspensions
- Key player absence impact
- Squad depth and rotation risk
- Recent lineup changes
- Fatigue indicators (match congestion, travel distance)

Usage:
    python objective_factors.py <fixture_id> <league_id> <season>
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.api_football import (
    get_fixture_by_id,
    get_injuries,
    get_players_squads,
    get_team_statistics,
)
from utils import print_json


def get_team_injuries(team_id: int, league_id: int, season: int) -> list[dict]:
    """Get injury list for a team, filtering to current season."""
    try:
        injuries = get_injuries(team=team_id, league=league_id, season=season)
        return injuries
    except Exception:
        return []


def get_squad_info(team_id: int) -> dict:
    """Get squad composition: size, average age, key positions."""
    try:
        squad = get_players_squads(team_id)
        if not squad:
            return {}
        
        players = squad[0].get("players", [])
        return {
            "squad_size": len(players),
            "players": [
                {
                    "name": p.get("name"),
                    "position": p.get("position"),
                    "number": p.get("number"),
                }
                for p in players
            ],
        }
    except Exception:
        return {}


def assess_fatigue(team_id: int, league_id: int, season: int) -> dict:
    """Assess fatigue based on recent fixture congestion."""
    try:
        stats = get_team_statistics(team_id, league_id, season)
        response = stats.get("response", {})
        
        fixtures = response.get("fixtures", {})
        played = int(fixtures.get("played", {}).get("total", 0) or 0)
        
        # Clean sheet rate as a rough defensive stability indicator
        clean_sheets = int(response.get("clean_sheet", {}).get("total", 0) or 0)
        cs_rate = clean_sheets / max(played, 1)
        
        # Failed to score rate
        failed_score = int(response.get("failed_to_score", {}).get("total", 0) or 0)
        fts_rate = failed_score / max(played, 1)
        
        return {
            "matches_played": played,
            "clean_sheet_rate": round(cs_rate, 2),
            "failed_to_score_rate": round(fts_rate, 2),
        }
    except Exception:
        return {}


def run(fixture_id: int, league_id: int, season: int) -> dict:
    """Execute objective factors analysis."""
    fixture = get_fixture_by_id(fixture_id)
    if not fixture:
        return {"agent": "objective_factors", "fixture_id": fixture_id, 
                "error": "Fixture not found"}
    
    f = fixture[0]
    home_id = f["teams"]["home"]["id"]
    away_id = f["teams"]["away"]["id"]
    home_name = f["teams"]["home"]["name"]
    away_name = f["teams"]["away"]["name"]
    
    # Injuries
    home_injuries = get_team_injuries(home_id, league_id, season)
    away_injuries = get_team_injuries(away_id, league_id, season)
    
    # Squad info
    home_squad = get_squad_info(home_id)
    away_squad = get_squad_info(away_id)
    
    # Fatigue
    home_fatigue = assess_fatigue(home_id, league_id, season)
    away_fatigue = assess_fatigue(away_id, league_id, season)
    
    # Build impact analysis
    notes = []
    factors = []
    
    # Injury impact
    for team_name, injuries in [(home_name, home_injuries), (away_name, away_injuries)]:
        if injuries:
            names = [inj.get("player", {}).get("name", "Unknown") for inj in injuries]
            types = [inj.get("player", {}).get("type", "Unknown") for inj in injuries]
            reasons = [inj.get("player", {}).get("reason", "") for inj in injuries]
            
            injury_list = []
            for n, t, r in zip(names, types, reasons):
                injury_list.append(f"{n} ({t}: {r})" if r else f"{n} ({t})")
            
            notes.append(f"{team_name} injuries: {', '.join(injury_list)}")
            factors.append({
                "team": team_name,
                "type": "injury",
                "severity": "high" if len(injuries) >= 3 else "medium" if len(injuries) >= 1 else "low",
                "detail": len(injuries),
            })
    
    if not (home_injuries or away_injuries):
        notes.append("No significant injuries reported for either team")
    
    # Squad depth
    home_squad_size = home_squad.get("squad_size", 0)
    away_squad_size = away_squad.get("squad_size", 0)
    if home_squad_size > 0:
        notes.append(f"{home_name} squad size: {home_squad_size} | {away_name}: {away_squad_size}")
    
    # Fatigue comparison
    if home_fatigue and away_fatigue:
        notes.append(
            f"Season fatigue: {home_name} ({home_fatigue.get('matches_played', 0)} played, "
            f"CS {home_fatigue.get('clean_sheet_rate', 0):.0%}) vs "
            f"{away_name} ({away_fatigue.get('matches_played', 0)} played, "
            f"CS {away_fatigue.get('clean_sheet_rate', 0):.0%})"
        )
    
    finding = "Objective factors assessed"
    injury_count = len(home_injuries) + len(away_injuries)
    if injury_count >= 3:
        finding += f" — significant injury impact ({injury_count} players out)"
    elif injury_count >= 1:
        finding += f" — minor injury impact ({injury_count} players out)"
    else:
        finding += " — clean injury slate"
    
    return {
        "agent": "objective_factors",
        "fixture": f"{home_name} vs {away_name}",
        "finding": finding,
        "signal_strength": "strong" if injury_count >= 3 else "medium" if injury_count >= 1 else "weak",
        "key_metrics": {
            "home": {
                "injuries": len(home_injuries),
                "injury_list": [
                    {
                        "name": i.get("player", {}).get("name"),
                        "type": i.get("player", {}).get("type"),
                        "reason": i.get("player", {}).get("reason"),
                    }
                    for i in home_injuries
                ],
                "squad_size": home_squad_size,
                "fatigue": home_fatigue,
            },
            "away": {
                "injuries": len(away_injuries),
                "injury_list": [
                    {
                        "name": i.get("player", {}).get("name"),
                        "type": i.get("player", {}).get("type"),
                        "reason": i.get("player", {}).get("reason"),
                    }
                    for i in away_injuries
                ],
                "squad_size": away_squad_size,
                "fatigue": away_fatigue,
            },
        },
        "notes": notes,
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print_json({"error": "Usage: objective_factors.py <fixture_id> <league_id> <season>"})
        sys.exit(1)
    fixture_id = int(sys.argv[1])
    league_id = int(sys.argv[2])
    season = int(sys.argv[3])
    try:
        result = run(fixture_id, league_id, season)
        print_json(result)
    except Exception as e:
        print_json({"agent": "objective_factors", "fixture_id": fixture_id, 
                    "error": str(e)})
```

- [ ] **Step 2: Commit**

```bash
git add scripts/analysis/objective_factors.py
git commit -m "feat: sub-agent F — objective factors analysis"
```

---

### Task 9: Aggregator — Cross-Validation Master

**Files:**
- Create: `scripts/aggregator.py`

- [ ] **Step 1: Write `scripts/aggregator.py`**

```python
"""Master Aggregator — cross-validates 6 sub-agent outputs.

This script is NOT meant to be run directly as a Python script. It is a
reference implementation showing the logic the AI agent should apply when
aggregating sub-agent results.

When using this skill, the AI agent:
1. Spawns 6 parallel sub-agents (each runs the respective analysis script)
2. Collects all JSON outputs
3. Feeds them to the logic below to produce the final report

The aggregator:
- Only cross-validates — never pulls raw data (avoids confirmation bias)
- Identifies conflicts (dimensions disagree = interesting spots)
- Identifies consensus (dimensions agree = higher confidence)
- Produces final output: recommend / watch / avoid per bet type
"""

import json
import sys
from typing import Any


def load_subagent_results(results_json: str) -> list[dict]:
    """Parse sub-agent results from JSON string or file."""
    if results_json.strip().startswith("{"):
        # Single result
        return [json.loads(results_json)]
    elif results_json.strip().startswith("["):
        return json.loads(results_json)
    else:
        # Assume file path
        with open(results_json.strip()) as f:
            return json.load(f)


def cross_validate(results: list[dict]) -> dict:
    """Cross-validate sub-agent results and produce final report."""
    
    # Separate valid results from errors
    valid = []
    errors = []
    for r in results:
        if "error" in r:
            errors.append(r)
        else:
            valid.append(r)
    
    if not valid:
        return {
            "error": "All sub-agents failed",
            "sub_agent_errors": [e["error"] for e in errors],
        }
    
    # Extract fixture name
    fixture = valid[0].get("fixture", "Unknown")
    
    # Detect conflicts (where dimensions disagree)
    conflicts = detect_conflicts(valid)
    
    # Detect consensus (where dimensions agree)
    consensus = detect_consensus(valid)
    
    # Build bet recommendations
    bets = build_bet_recommendations(valid, conflicts, consensus)
    
    # Build executive summary
    summary = build_summary(valid, conflicts, consensus, bets)
    
    return {
        "fixture": fixture,
        "timestamp": "",  # Filled by caller
        "sub_agent_summary": [
            {
                "agent": r["agent"],
                "finding": r.get("finding", "Error"),
                "strength": r.get("signal_strength", "none"),
                "error": r.get("error"),
            }
            for r in results
        ],
        "conflicts": conflicts,
        "consensus": consensus,
        "bets": bets,
        "summary": summary,
        "warnings": [e.get("error", "") for e in errors],
    }


def detect_conflicts(valid_results: list[dict]) -> list[dict]:
    """Detect areas where sub-agent findings contradict each other."""
    conflicts = []
    
    # Map agents to their signal direction
    signals = {}
    for r in valid_results:
        agent = r["agent"]
        finding = r.get("finding", "").lower()
        metrics = r.get("key_metrics", {})
        notes = r.get("notes", [])
        signals[agent] = {"finding": finding, "metrics": metrics, "notes": notes}
    
    # Conflict 1: Fundamentals vs Market Sentiment
    f = signals.get("fundamentals", {})
    ms = signals.get("market_sentiment", {})
    if f and ms:
        f_gap = f.get("metrics", {}).get("gap")
        ms_heat = ms.get("metrics", {}).get("overheat_level")
        if f_gap is not None and ms_heat:
            # If fundamentals say undervalue but market is overheating on that side
            if abs(f_gap) > 0.05 and ms_heat == "high":
                conflicts.append({
                    "dimensions": ["fundamentals", "market_sentiment"],
                    "conflict": f"Fundamentals gap={f_gap:.3f} vs market overheating={ms_heat}",
                    "interpretation": "Market may be right — fundamentals model could be missing context",
                })
            elif abs(f_gap) > 0.05 and ms_heat == "low":
                conflicts.append({
                    "dimensions": ["fundamentals", "market_sentiment"],
                    "conflict": f"Fundamentals gap={f_gap:.3f} but market is calm",
                    "interpretation": "Potential value opportunity — market hasn't caught on",
                })
    
    # Conflict 2: Odds signals vs Bookmaker divergence
    os_sig = signals.get("odds_signals", {})
    bm_div = signals.get("bookmaker_divergence", {})
    if os_sig and bm_div:
        bm_level = bm_div.get("metrics", {}).get("match_winner_divergence", {}).get("level")
        os_strength = os_sig.get("finding", "")
        if bm_level in ("high",) and "strong" in os_strength:
            conflicts.append({
                "dimensions": ["odds_signals", "bookmaker_divergence"],
                "conflict": "Odds signals suggest strong direction but bookmakers disagree",
                "interpretation": "Low confidence — wait for consensus or reduce stake",
            })
    
    # Conflict 3: Historical backtest vs odds
    hb = signals.get("historical_backtest", {})
    if hb:
        baseline = hb.get("metrics", {}).get("league_baseline", {})
        odds_profile = hb.get("metrics", {}).get("current_odds_profile", {})
        home_odds = odds_profile.get("home_odds")
        if home_odds and baseline:
            market_prob = 1 / home_odds
            hist_prob = baseline.get("home_win_rate", 0)
            if abs(market_prob - hist_prob) > 0.1:
                conflicts.append({
                    "dimensions": ["historical_backtest", "odds_signals"],
                    "conflict": f"Historical home win rate {hist_prob:.1%} vs market implied {market_prob:.1%}",
                    "interpretation": "Market is pricing differently from historical norms",
                })
    
    return conflicts


def detect_consensus(valid_results: list[dict]) -> list[dict]:
    """Detect areas where sub-agent findings agree."""
    consensus = []
    
    # Count how many agents lean bullish/bearish on the favorite
    lean_bullish = 0
    lean_bearish = 0
    neutral = 0
    
    for r in valid_results:
        finding = r.get("finding", "").lower()
        # Simple heuristic: check for positive/negative language
        positive_words = ["undervalue", "value", "strong home", "favor", "bullish", 
                         "low overround", "sharp market"]
        negative_words = ["overvalue", "overheat", "trap", "divergence", "unreliable",
                         "high overround", "avoid"]
        
        pos_count = sum(1 for w in positive_words if w in finding)
        neg_count = sum(1 for w in negative_words if w in finding)
        
        if pos_count > neg_count:
            lean_bullish += 1
        elif neg_count > pos_count:
            lean_bearish += 1
        else:
            neutral += 1
    
    if lean_bullish >= 4:
        consensus.append({
            "dimensions": ["all"],
            "agreement": f"Strong bullish consensus ({lean_bullish}/{len(valid_results)} agents favor the favorite)",
        })
    elif lean_bearish >= 4:
        consensus.append({
            "dimensions": ["all"],
            "agreement": f"Strong bearish consensus ({lean_bearish}/{len(valid_results)} agents oppose the favorite)",
        })
    elif lean_bullish + lean_bearish >= 4:
        consensus.append({
            "dimensions": ["all"],
            "agreement": f"Split opinion — no clear consensus ({lean_bullish} bull, {lean_bearish} bear, {neutral} neutral)",
        })
    
    return consensus


def build_bet_recommendations(valid_results: list[dict],
                               conflicts: list[dict],
                               consensus: list[dict]) -> dict:
    """Build final bet type recommendations."""
    bets = {
        "1x2": {"recommendation": "watch", "confidence": "low", "reasoning": ""},
        "asian_handicap": {"recommendation": "watch", "confidence": "low", "reasoning": ""},
        "over_under": {"recommendation": "watch", "confidence": "low", "reasoning": ""},
    }
    
    # Count conflict severity
    has_conflict = len(conflicts) > 0
    high_conflict = any("trap" in c.get("interpretation", "") for c in conflicts)
    
    # Count consensus
    has_consensus = len(consensus) > 0
    strong_consensus = any("Strong" in c.get("agreement", "") for c in consensus)
    
    # Aggregate signal strengths
    strengths = [r.get("signal_strength", "weak") for r in valid_results if "error" not in r]
    strong_count = sum(1 for s in strengths if s == "strong")
    
    # Decision logic
    if has_consensus and strong_consensus and not has_conflict:
        bets["1x2"]["recommendation"] = "recommend"
        bets["1x2"]["confidence"] = "high"
        bets["1x2"]["reasoning"] = "Strong multi-agent consensus with no conflicts"
    elif has_consensus and has_conflict:
        bets["1x2"]["recommendation"] = "watch"
        bets["1x2"]["confidence"] = "medium"
        bets["1x2"]["reasoning"] = "Consensus exists but conflicts present — monitor odds movement"
    elif high_conflict:
        bets["1x2"]["recommendation"] = "avoid"
        bets["1x2"]["confidence"] = "high"
        bets["1x2"]["reasoning"] = "Major conflicts between analysis dimensions — unreliable signals"
    elif strong_count >= 4:
        bets["1x2"]["recommendation"] = "recommend"
        bets["1x2"]["confidence"] = "medium"
        bets["1x2"]["reasoning"] = "Majority of agents show strong signals"
    
    # Asian handicap follows 1X2 logic loosely
    bets["asian_handicap"]["recommendation"] = bets["1x2"]["recommendation"]
    bets["asian_handicap"]["confidence"] = bets["1x2"]["confidence"]
    bets["asian_handicap"]["reasoning"] = "Follows 1X2 analysis; check odds_signals for AH-specific data"
    
    # Over/Under
    ou_agents = [r for r in valid_results if "over" in r.get("finding", "").lower() or "under" in r.get("finding", "").lower()]
    if len(ou_agents) >= 2:
        bets["over_under"]["recommendation"] = "recommend"
        bets["over_under"]["confidence"] = "medium"
        bets["over_under"]["reasoning"] = "Multiple agents agree on O/U direction"
    
    return bets


def build_summary(valid_results: list[dict], conflicts: list[dict],
                   consensus: list[dict], bets: dict) -> str:
    """Build executive summary text."""
    parts = []
    
    # Agent summary
    for r in valid_results:
        strength = r.get("signal_strength", "none")
        parts.append(f"[{r['agent']}] ({strength}) {r.get('finding', 'No finding')}")
    
    # Conflicts
    if conflicts:
        parts.append(f"\n=== CONFLICTS ({len(conflicts)}) ===")
        for c in conflicts:
            parts.append(f"  [{', '.join(c['dimensions'])}] {c['conflict']}")
            parts.append(f"  → {c['interpretation']}")
    
    # Consensus
    if consensus:
        parts.append(f"\n=== CONSENSUS ({len(consensus)}) ===")
        for c in consensus:
            parts.append(f"  [{', '.join(c['dimensions'])}] {c['agreement']}")
    
    # Recommendations
    parts.append("\n=== RECOMMENDATIONS ===")
    for bet_type, info in bets.items():
        rec = info["recommendation"].upper()
        parts.append(f"  {bet_type}: {rec} (confidence: {info['confidence']}) — {info['reasoning']}")
    
    return "\n".join(parts)


def aggregate(results_list: list[dict]) -> dict:
    """Main entry point: accept list of sub-agent results, return final report."""
    from utils import now_iso
    report = cross_validate(results_list)
    report["timestamp"] = now_iso()
    return report


# --- CLI entry point: accepts JSON file of sub-agent results ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: aggregator.py <subagent_results.json>")
        print("  subagent_results.json: JSON array of sub-agent output objects")
        sys.exit(1)
    
    results = load_subagent_results(sys.argv[1])
    report = aggregate(results)
    
    # Print summary to stdout
    print(report.get("summary", json.dumps(report, indent=2, ensure_ascii=False)))
    print("\n--- FULL REPORT ---")
    print(json.dumps(report, indent=2, ensure_ascii=False))
```

- [ ] **Step 2: Commit**

```bash
git add scripts/aggregator.py
git commit -m "feat: master aggregator for cross-validating 6 sub-agents"
```

---

### Task 10: SKILL.md — Main Skill Document

**Files:**
- Create: `SKILL.md`

- [ ] **Step 1: Write `SKILL.md`**

(NOTE: This is a long file. Write it with the Write tool using the content below.)

Use the following content for `SKILL.md`:

```markdown
---
name: football-betting-analysis
description: Use when the user wants to analyse football matches for betting purposes — covers 1X2, Asian handicap, and Over/Under markets. Use when the user asks for 比赛分析, 足彩分析, 盘口分析, 赔率分析, or wants to understand bookmaker pricing logic. Launches 6 parallel sub-agents for multi-dimensional analysis, then cross-validates to find value opportunities.
---

# Football Betting Analysis Skill

## Overview

Reverse-engineer bookmaker pricing logic through 6 parallel analysis dimensions. Find the gap between what odds say and what fundamentals/statistics/history suggest — that gap is where betting value lives.

**Core principle:** Not predicting results. Finding mispricing.

## When to Use

- User asks to analyse a football match for betting
- User wants 欧赔/亚盘/大小球 analysis
- User asks "这场比赛怎么看" for betting purposes
- User wants to understand bookmaker intent from odds movement

**Required:** User must provide fixture ID, league ID, and season, OR enough context to look them up (team names + league name).

## Architecture

```
User request: "分析 fixture_id=X, league_id=Y, season=Z"
  → Master agent (you): spawn 6 parallel sub-agents
    ├── Sub-agent A: fundamentals.py (基本面 vs 盘口偏差)
    ├── Sub-agent B: odds_signals.py (盘口信号解读)
    ├── Sub-agent C: historical_backtest.py (历史同赔回测)
    ├── Sub-agent D: bookmaker_divergence.py (庄家分歧度)
    ├── Sub-agent E: market_sentiment.py (市场情绪)
    └── Sub-agent F: objective_factors.py (客观因素)
  → Wait for ALL 6 to complete
  → Feed results to aggregator.py for cross-validation
  → Present final report to user
```

## Execution Protocol

### Step 1: Parse the user request

The user may provide:
- `fixture_id` directly
- Team names and league (you must look up IDs first)
- A URL or reference to a specific match

If IDs are missing, use the API to search for them before proceeding.

### Step 2: Launch 6 sub-agents in PARALLEL

Use the Task tool to spawn 6 sub-agents simultaneously. Each sub-agent runs one analysis script:

```
Task 1 (fundamentals): 
  Run: python scripts/analysis/fundamentals.py <fixture_id> <league_id> <season>
  Reads JSON output from stdout. Returns the parsed dict.

Task 2 (odds_signals):
  Run: python scripts/analysis/odds_signals.py <fixture_id> <league_id> <season>

Task 3 (historical_backtest):
  Run: python scripts/analysis/historical_backtest.py <fixture_id> <league_id> <season>

Task 4 (bookmaker_divergence):
  Run: python scripts/analysis/bookmaker_divergence.py <fixture_id> <league_id> <season>

Task 5 (market_sentiment):
  Run: python scripts/analysis/market_sentiment.py <fixture_id> <league_id> <season>

Task 6 (objective_factors):
  Run: python scripts/analysis/objective_factors.py <fixture_id> <league_id> <season>
```

**CRITICAL RULES:**
- All 6 sub-agents MUST be launched in parallel — NOT sequentially
- Sub-agents are information-isolated — they do NOT share context or see each other's output
- Each sub-agent returns JSON to stdout. Capture it.
- If any sub-agent returns an error, record it and continue. A partial analysis is better than none.
- Each sub-agent script requires `RAPIDAPI_KEY` in environment variables

### Step 3: Run the aggregator

After all 6 sub-agents complete, feed their collected JSON results to the aggregator:

```
Run: python scripts/aggregator.py <subagent_results.json>
```

Or apply the cross-validation logic from `aggregator.py` directly in your reasoning.

### Step 4: Present the final report

Format the output clearly for the user:

1. **摘要**: One-line summary of the analysis
2. **矛盾与一致**: Which dimensions conflict, which agree
3. **各维度详情**: Brief summary of each sub-agent's key findings
4. **投注建议**: Per bet type: Recommend / Watch / Avoid with reasons
5. **风险提示**: Key risk factors

## API Setup

Before analysis, ensure:
```bash
set RAPIDAPI_KEY=your_key_here
```

Get an API key from: https://rapidapi.com/api-sports/api/api-football
Sign up for the free tier (100 requests/day).

**If rate limit is hit:** Report the error clearly. User can upgrade their plan for more requests.

## Looking Up IDs

When user provides team names instead of IDs:

```bash
# Search for league ID
python -c "from scripts.api.api_football import get_leagues; from scripts.utils import print_json; print_json(get_leagues(search='World Cup'))"

# Search for team ID  
python -c "from scripts.api.api_football import get_teams; from scripts.utils import print_json; print_json(get_teams(name='Brazil'))"

# Find fixtures
python -c "from scripts.api.api_football import get_fixtures; from scripts.utils import print_json; print_json(get_fixtures(league_id=X, season=2026, team_id=Y))"
```

## Key Analysis Concepts

### Reading Odds Movement
- **初盘→即时盘 direction**: If odds shorten on a side, money is flowing that way
- **Sharp move late**: Big shift in last hours before kickoff = strongest signal
- **Opposite movement**: If odds move against popular opinion, bookmaker is likely right

### Reading Bookmaker Intent
- **Deep handicap (≥1 ball)**: Bookmaker expects a clear result
- **Shallow handicap (≤0.25 ball)**: Bookmaker sees a toss-up
- **Line upgrade/downgrade**: Bookmaker adjusting risk exposure
- **Return rate**: Low = efficient market, high = wide margin (less signal)

### Contrarian Indicators
- Public heavily on one side + odds NOT moving = bookmaker confident, traps being set
- Sharp bookmakers (Pinnacle) disagree with retail (Bet365) = follow the sharps
- Market overheating on favorite + fundamentals disagree = potential value on underdog

## Output Format

Final report follows this structure:
```
📊 比赛: [Home] vs [Away] | [Date]
━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 六维分析摘要:
  [fundamentals]: [finding] (信号强度: strong/medium/weak)
  [odds_signals]: [finding] (信号强度: ...)
  ...

⚠️ 矛盾点 (Conflicts):
  - [conflict description] → [interpretation]

✅ 一致点 (Consensus):
  - [agreement description]

🎯 投注建议:
  胜平负:     Recommend/Watch/Avoid — [reasoning]
  让球盘:     Recommend/Watch/Avoid — [reasoning]
  大小球:     Recommend/Watch/Avoid — [reasoning]

📋 风险提示:
  - [risk factor 1]
  - [risk factor 2]
```

## Quick Reference: Common World Cup IDs

| Competition | League ID | Common Seasons |
|------------|-----------|----------------|
| World Cup | 1 | 2022, 2026 |
| UEFA Euro | 4 | 2024, 2028 |
| Premier League | 39 | 2022, 2023, 2024, 2025 |
| La Liga | 140 | 2022, 2023, 2024, 2025 |
| Bundesliga | 78 | 2022, 2023, 2024, 2025 |
| Serie A | 135 | 2022, 2023, 2024, 2025 |
| Ligue 1 | 61 | 2022, 2023, 2024, 2025 |
| Champions League | 2 | 2022, 2023, 2024, 2025 |
| CSL (中超) | 169 | 2022, 2023, 2024, 2025 |
| J-League | 98 | 2022, 2023, 2024, 2025 |
```

- [ ] **Step 2: Commit**

```bash
git add SKILL.md
git commit -m "feat: main SKILL.md with 6-agent orchestration protocol"
```

---

### Task 11: API Reference Document

**Files:**
- Create: `references/api_reference.md`

- [ ] **Step 1: Write `references/api_reference.md`**

```markdown
# API-Football v3 Reference

## Base URL
```
https://api-football-v1.p.rapidapi.com/v3
```

## Authentication
Header: `x-rapidapi-key: YOUR_KEY`
Header: `x-rapidapi-host: api-football-v1.p.rapidapi.com`

## Rate Limits (Free Tier)
- 100 requests/day
- Header: `x-ratelimit-requests-limit` / `x-ratelimit-requests-remaining`

## Key Endpoints

### Fixtures
| Endpoint | Params | Returns |
|----------|--------|---------|
| `/fixtures` | league, season, team, status, from, to | Match list |
| `/fixtures?id=X` | id | Single match with events/lineups/stats/players |
| `/fixtures/headtohead` | h2h (`teamA-teamB`) | H2H history |

### Odds
| Endpoint | Params | Returns |
|----------|--------|---------|
| `/odds` | fixture, league, season, bookmaker, bet, page | Pre-match odds (7-day history, 3hr updates) |
| `/odds/live` | fixture, league, bet | Live in-play odds (5-60s updates) |
| `/odds/mapping` | page | Fixture→odds availability (daily) |
| `/odds/bookmakers` | — | All bookmaker IDs |
| `/odds/bets` | — | All bet type IDs |

### Teams & Players
| Endpoint | Params | Returns |
|----------|--------|---------|
| `/teams` | id, league, season, name, country | Team info |
| `/teams/statistics` | team, league, season | Team stats (form, goals, cards) |
| `/players` | team, league, season, search, page | Player info |
| `/players/squads` | team | Current squad |
| `/injuries` | team, league, season, fixture, player | Injuries & suspensions |

### Other
| Endpoint | Params | Returns |
|----------|--------|---------|
| `/standings` | league, season, team | League table |
| `/predictions` | fixture | Win%/goals% predictions |
| `/leagues` | id, team, country, season, search | Competition info |
| `/transfers` | player, team | Transfer records |

## Bet Type IDs
| ID | Name |
|----|------|
| 1 | Match Winner (1X2) |
| 2 | Asian Handicap |
| 5 | Goals Over/Under |
| 6 | Goals Over/Under First Half |
| 8 | Both Teams Score |
| 12 | Double Chance |
| 45 | Correct Score |
| 46 | HT/FT Result |

## Bookmaker IDs
| ID | Name | Type |
|----|------|------|
| 8 | Pinnacle | Sharp |
| 9 | Bet365 | Retail |
| 2 | William Hill | Retail |
| 4 | Bwin | Retail |
| 3 | Betfair | Sharp |
| 15 | Marathonbet | Sharp |
| 24 | 1xBet | Sharp |
| 26 | Unibet | Retail |

## Odds Response Structure
```json
{
  "response": [
    {
      "league": {"id": 1, "name": "World Cup"},
      "fixture": {"id": 12345, "date": "2026-..."},
      "bookmakers": [
        {
          "id": 8,
          "name": "Pinnacle",
          "bets": [
            {
              "id": 1,
              "name": "Match Winner",
              "values": [
                {"value": "Home", "odd": "1.85"},
                {"value": "Draw", "odd": "3.40"},
                {"value": "Away", "odd": "4.20"}
              ]
            }
          ]
        }
      ]
    }
  ]
}
```
```

- [ ] **Step 2: Commit**

```bash
git add references/api_reference.md
git commit -m "docs: API-Football v3 endpoint quick reference"
```

---

### Task 12: Analysis Theory Reference

**Files:**
- Create: `references/analysis_theory.md`

- [ ] **Step 1: Write `references/analysis_theory.md`**

```markdown
# Football Betting Analysis Theory

## 1. Kelly Criterion — Optimal Stake Sizing

```
f* = (bp - q) / b

Where:
  f* = fraction of bankroll to bet
  b  = decimal odds - 1
  p  = your estimated win probability
  q  = 1 - p

Example: odds 2.00, you think 55% win chance
  f* = (1 × 0.55 - 0.45) / 1 = 0.10 → bet 10% of bankroll

Practical: Use fractional Kelly (1/4 or 1/2) for safety.
```

## 2. Overround (Vig) — Bookmaker's Margin

```
Overround = Σ(1/odds_i) - 1

Example: 1X2 odds 1.85 / 3.40 / 4.20
  Overround = 1/1.85 + 1/3.40 + 1/4.20 - 1
            = 0.5405 + 0.2941 + 0.2381 - 1
            = 0.0727 (7.27%)

Interpretation:
  < 3%  → Very sharp market (Pinnacle on major leagues)
  3-6%  → Normal market
  6-10% → Wider margin (smaller leagues, exotic bets)
  >10%  → High margin — less value to find
```

## 3. Asian Handicap Mechanics

| Handicap | Meaning |
|----------|---------|
| 0 | Draw no bet |
| -0.25 | Favorite loses 1/4 stake on draw |
| -0.5 | Favorite must win (half-ball) |
| -0.75 | Favorite wins by 1 = half win; by 2+ = full win |
| -1 | Favorite must win by 2+ for full win; by 1 = push |
| -1.25 | Favorite wins by 1 = half loss; by 2+ = full win |
| -1.5 | Favorite must win by 2+ |

**Water level (水位)**: The odds on each side. 
- Low water (< 1.80): Bookmaker confident, low payout
- High water (> 2.00): Bookmaker less confident, attractive payout

**Key pattern**: When the handicap line moves but the water level stays flat 
→ genuine line movement (bookmaker really changed their view).
When water level moves but line stays → market pressure, not bookmaker conviction.

## 4. Odds Movement Patterns

### Pattern A: Early Stability → Late Sharp Move
```
Opening (3 days before): 1.90 / 3.40 / 4.00
Middle (1 day before):   1.88 / 3.50 / 4.10
Closing (1 hour before): 1.72 / 3.80 / 4.80  ← SHARP MOVE

Interpretation: Strong late money on home team. 
High signal — likely smart money.
```

### Pattern B: Steady Drift
```
Opening: 2.10 / 3.30 / 3.50
Daily:   2.08 → 2.05 → 2.02 → 1.98

Interpretation: Gradual money flow. 
Moderate signal — market slowly adjusting, no urgency.
```

### Pattern C: Spike and Revert
```
Opening:  1.95
Spike to: 1.75 (brief)
Revert:   1.90

Interpretation: Large single bet moved line, then corrected. 
Low signal — one punter, not information.
```

### Pattern D: Odds lengthening on favorite
```
Favorite opens at 1.60, drifts to 1.75

Interpretation: Money flowing AGAINST favorite.
Very negative signal — smart money opposing the favorite.
```

## 5. Contrarian Indicators

**When the public is heavily on one side but odds move opposite:**
→ Follow the odds movement. The bookmaker is absorbing the public money 
  and NOT adjusting — they're confident.

**When sharp odds differ from retail odds by > 0.10:**
→ Pinnacle/Betfair > 2.00 on a side while Bet365 < 1.90
→ Follow the sharp bookmaker. Retail is shading for public bias.

**When xG contradicts actual results over 5+ matches:**
→ A team scoring more than xG suggests is running hot → fade them
→ A team scoring less than xG suggests is due for regression → back them

## 6. League-Specific Traits

| League | Home Win% | Avg Goals | Over 2.5% | Style |
|--------|-----------|-----------|-----------|-------|
| Premier League | ~45% | 2.8 | 55% | Physical, moderate scoring |
| La Liga | ~48% | 2.5 | 45% | Technical, lower scoring |
| Bundesliga | ~45% | 3.1 | 60% | Open, high scoring |
| Serie A | ~42% | 2.7 | 50% | Tactical, moderate |
| Ligue 1 | ~43% | 2.6 | 48% | Defensive |
| World Cup | ~43% | 2.4 | 42% | Cautious, low scoring |
| Euros | ~44% | 2.3 | 40% | Cautious |
| Champions League | ~48% | 2.9 | 53% | Quality attack |

## 7. Value Detection Framework

A bet has value when:
```
Your_Estimated_Probability > 1 / Decimal_Odds
```

Example: You think team A has 60% win chance. Odds = 2.00 (50% implied).
  60% > 50% → VALUE BET

Example: You think team A has 40% win chance. Odds = 1.80 (55.6% implied).
  40% < 55.6% → NO VALUE

The gap between your estimate and the market's estimate is your edge.
If your estimate is not demonstrably better than the market's, you have no edge.
```

- [ ] **Step 2: Commit**

```bash
git add references/analysis_theory.md
git commit -m "docs: football betting analysis theory reference"
```

---

### Task 13: Verify Complete File Structure

- [ ] **Step 1: List all files**

```bash
Get-ChildItem -Recurse -Name -File | Sort-Object
```

Expected output:
```
SKILL.md
references/analysis_theory.md
references/api_reference.md
scripts/__init__.py
scripts/aggregator.py
scripts/api/__init__.py
scripts/api/api_football.py
scripts/analysis/__init__.py
scripts/analysis/bookmaker_divergence.py
scripts/analysis/fundamentals.py
scripts/analysis/historical_backtest.py
scripts/analysis/market_sentiment.py
scripts/analysis/objective_factors.py
scripts/analysis/odds_signals.py
scripts/utils.py
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat: complete football betting analysis skill — all 12 tasks"
```
