"""Sub-Agent C: Historical Odds Pattern Backtest.

For a given fixture, searches past seasons of the same league for finished
matches and computes baseline stats. Compares current odds implied probability
against historical rates.

Data sources:
- football-data.org for match details + historical finished matches
- The Odds API for current odds

Usage:
    python historical_backtest.py <match_id> <competition_id> <season>
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.football_data import get_match, get_matches
from api.odds_api import get_odds, extract_h2h_odds, extract_spreads, extract_totals
from utils import print_json, implied_probability

COMP_TO_SPORT = {
    "PL": "soccer_epl",
    "BL1": "soccer_germany_bundesliga",
    "SA": "soccer_italy_serie_a",
    "PD": "soccer_spain_la_liga",
    "FL1": "soccer_france_ligue_one",
    "CL": "soccer_uefa_champs_league",
}


def get_current_odds_profile(sport_key: str, home_name: str, away_name: str) -> dict:
    """Extract the odds profile for the current fixture using The Odds API."""
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

    if not sport_key:
        return profile

    odds_data = get_odds(sport_key)
    if not odds_data:
        return profile

    h2h = extract_h2h_odds(odds_data, home_name, away_name)
    if h2h:
        first_bm = next(iter(h2h.values()))
        profile["home_odds"] = first_bm.get("Home")
        profile["draw_odds"] = first_bm.get("Draw")
        profile["away_odds"] = first_bm.get("Away")

    spreads = extract_spreads(odds_data, home_name, away_name)
    if spreads:
        first_bm = next(iter(spreads.values()))
        for team_name, data in first_bm.items():
            if profile["ah_home_odds"] is None and team_name == home_name:
                profile["ah_home_odds"] = data["price"]
                profile["ah_line"] = data.get("point")
            elif profile["ah_away_odds"] is None and team_name == away_name:
                profile["ah_away_odds"] = data["price"]

    totals = extract_totals(odds_data, home_name, away_name)
    if totals:
        first_bm = next(iter(totals.values()))
        over_data = first_bm.get("Over")
        under_data = first_bm.get("Under")
        if over_data:
            profile["ou_over_odds"] = over_data["price"]
            profile["ou_line"] = over_data.get("point")
        if under_data:
            profile["ou_under_odds"] = under_data["price"]

    return profile


def fetch_historical_matches(competition_id: str, season: int) -> list[dict]:
    """Get finished matches from the previous season as baseline.

    Grabs Aug-Oct of the prior season (2-3 months) to minimize API calls.
    Falls back to 2 seasons back if too few matches.
    """
    finished = []
    for offset in (1, 2):
        past_year = season - offset
        date_from = f"{past_year}-08-01"
        date_to = f"{past_year}-11-01"
        try:
            matches = get_matches(
                competition_id,
                date_from=date_from,
                date_to=date_to,
                status="FINISHED",
            )
            finished.extend(matches)
        except Exception:
            continue
        if len(finished) >= 20:
            break
    return finished


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

    for f in fixtures:
        score = f.get("score", {}) or {}
        ft = score.get("fullTime", {}) or {}
        home_g = ft.get("home") or 0
        away_g = ft.get("away") or 0

        total_goals += home_g + away_g
        if home_g + away_g > 2.5:
            over_25 += 1

        if home_g > away_g:
            home_wins += 1
        elif home_g == away_g:
            draws += 1
        else:
            away_wins += 1

    n = max(total, 1)
    return {
        "total_matches": total,
        "home_win_rate": round(home_wins / n, 3),
        "draw_rate": round(draws / n, 3),
        "away_win_rate": round(away_wins / n, 3),
        "avg_goals": round(total_goals / n, 2),
        "over_25_rate": round(over_25 / n, 3),
        "under_25_rate": round((total - over_25) / n, 3),
    }


def run(match_id: int, competition_id: str, season: int) -> dict:
    """Execute historical pattern backtest."""
    match_detail = get_match(match_id)
    if not match_detail:
        return {
            "agent": "historical_backtest",
            "match_id": match_id,
            "error": "Match not found",
        }

    home_name = match_detail["homeTeam"]["name"]
    away_name = match_detail["awayTeam"]["name"]

    sport_key = COMP_TO_SPORT.get(competition_id)
    profile = get_current_odds_profile(sport_key, home_name, away_name)

    past_fixtures = fetch_historical_matches(competition_id, season)
    baseline = compute_baseline_stats(past_fixtures)

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
        notes.append(
            f"Based on {baseline['total_matches']} historical matches in this league "
            f"(home win {baseline['home_win_rate']:.1%}, "
            f"avg {baseline['avg_goals']} goals, "
            f"over 2.5: {baseline['over_25_rate']:.1%})"
        )

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
        print_json({"error": "Usage: historical_backtest.py <match_id> <competition_id> <season>"})
        sys.exit(1)
    match_id = int(sys.argv[1])
    competition_id = sys.argv[2]
    season = int(sys.argv[3])
    try:
        result = run(match_id, competition_id, season)
        print_json(result)
    except Exception as e:
        print_json({"agent": "historical_backtest", "match_id": match_id, "error": str(e)})
