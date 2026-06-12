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
