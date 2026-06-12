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
