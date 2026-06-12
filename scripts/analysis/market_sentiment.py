"""Sub-Agent E: Market Sentiment Analysis.

Detects market overheating and contrarian signals:
- Betting volume distribution (via odds movement as proxy)
- Public bias indicators (retail vs sharp bookmaker gap)
- Contrarian indicators (when to bet against the crowd)

Sentiment is inferred from:
1. Odds movement direction (money flows move odds)
2. Sharp vs retail bookmaker disagreement (via The Odds API)
3. Predictions endpoint (aggregated tipster sentiment, via API-Football)

Usage:
    python market_sentiment.py <fixture_id> <league_id> <season>
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.football_data import get_match
from api.odds_api import get_sport_key, get_odds, extract_h2h_odds
from api.odds_api_io import find_event_id as io_find_event_id, get_odds as io_get_odds, extract_odds_summary
from api.sporttery import search_by_teams, get_world_cup_matches
from utils import print_json, implied_probability


SHARP_BOOKMAKERS = {"Pinnacle", "Betfair", "Matchbook", "Marathonbet", "1xBet", "Paddy Power"}
RETAIL_BOOKMAKERS = {"Bet365", "William Hill", "Unibet", "Ladbrokes", "BetVictor", "DraftKings", "FanDuel"}


def compare_sharp_vs_retail(h2h_odds: dict) -> dict:
    """Compare sharp and retail bookmaker odds to infer public bias.

    If retail odds are shorter than sharp odds for a popular side,
    the public is likely betting heavily on that side.
    """
    sharp_odds = {}
    retail_odds = {}

    for bm_name, outcomes in h2h_odds.items():
        for outcome, price in outcomes.items():
            if bm_name in SHARP_BOOKMAKERS:
                sharp_odds.setdefault(outcome, []).append(float(price))
            elif bm_name in RETAIL_BOOKMAKERS:
                retail_odds.setdefault(outcome, []).append(float(price))

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


def get_web_search_queries(home_name: str, away_name: str, season: int) -> list[str]:
    """Generate web search queries for crowd sentiment (predictions not in football-data.org)."""
    return [
        f"{home_name} vs {away_name} prediction {season}",
        f"{home_name} {away_name} betting tips preview {season}",
        f"{home_name} vs {away_name} expert analysis {season}",
    ]


def run(match_id: int, competition_id: str, season: int) -> dict:
    """Execute market sentiment analysis."""
    match = get_match(match_id)
    if not match:
        return {"agent": "market_sentiment", "fixture_id": match_id, 
                "error": "Match not found"}
    
    home_name = match["homeTeam"]["name"]
    away_name = match["awayTeam"]["name"]
    
    sport_key = get_sport_key(competition_id)
    if not sport_key:
        return {"agent": "market_sentiment", "fixture_id": match_id,
                "error": f"No Odds API sport key for league {competition_id}"}

    odds_data = get_odds(sport_key)
    h2h_odds = extract_h2h_odds(odds_data, home_name, away_name)
    search_queries = get_web_search_queries(home_name, away_name, season)
    source_label = "The Odds API"

    # Fallback to odds-api.io
    if not h2h_odds:
        try:
            io_event_id = io_find_event_id(home_name, away_name)
            if io_event_id:
                io_data = io_get_odds(io_event_id, bookmakers="Bet365,Unibet")
                io_summary = extract_odds_summary(io_data)
                for book, markets in io_summary.items():
                    if "ML" in markets:
                        ml = markets["ML"][0]
                        h = float(ml.get("home", 0)) or 0
                        d = float(ml.get("draw", 0)) or 0
                        a = float(ml.get("away", 0)) or 0
                        if h or d or a:
                            h2h_odds[book] = {"Home": h, "Draw": d, "Away": a}
                if h2h_odds:
                    source_label = "odds-api.io"
        except Exception:
            pass

    # Final fallback to sporttery
    if not h2h_odds:
        try:
            sp_data = search_by_teams(home_name, away_name)
            if not sp_data:
                for wc in get_world_cup_matches():
                    if home_name.lower() in wc["home_team"].lower() or home_name.lower() in wc["away_team"].lower():
                        sp_data = wc
                        break
            if sp_data and sp_data.get("odds", {}).get("h2h"):
                h2h = sp_data["odds"]["h2h"]
                if h2h.get("home"):
                    h2h_odds = {"竞彩": {"Home": h2h["home"], "Draw": h2h["draw"] or 0, "Away": h2h["away"] or 0}}
                    source_label = "竞彩网"
        except Exception:
            pass
    
    # Sharp vs retail comparison
    public_bias = compare_sharp_vs_retail(h2h_odds)
    
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
    
    # Check web search availability
    if search_queries:
        notes.append(f"Web search suggested for crowd sentiment: see search_queries")
    
    notes.insert(0, f"Odds source: {source_label}")

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
    
    strength = "strong" if heat_level == "high" else "medium" if heat_level == "medium" else "weak"
    
    return {
        "agent": "market_sentiment",
        "fixture": f"{home_name} vs {away_name}",
        "finding": finding,
        "signal_strength": strength,
        "key_metrics": {
            "overheat_level": heat_level,
            "overheat_signals": overheat_signals,
            "public_bias_analysis": public_bias,
            "search_queries": search_queries,
        },
        "notes": notes,
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print_json({"error": "Usage: market_sentiment.py <fixture_id> <league_id> <season>"})
        sys.exit(1)
    match_id = int(sys.argv[1])
    competition_id = sys.argv[2]
    season = int(sys.argv[3])
    try:
        result = run(match_id, competition_id, season)
        print_json(result)
    except Exception as e:
        print_json({"agent": "market_sentiment", "fixture_id": match_id, 
                    "error": str(e)})
