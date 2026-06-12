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
