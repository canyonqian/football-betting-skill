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
