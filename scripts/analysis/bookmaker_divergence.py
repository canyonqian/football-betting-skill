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
