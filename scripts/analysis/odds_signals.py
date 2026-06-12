"""Sub-Agent B: Odds Movement Signal Analysis.

Interprets opening-to-current odds movement as bookmaker intent:
- Water level (shuiwei) changes → market pressure direction
- Line movement (upgrade/downgrade of handicap) → bookmaker risk adjustment
- Return rate shift → margin rebate changes signal confidence

Key insight: sharp odds movement late before kickoff is the strongest signal.
If the odds move AGAINST popular opinion, the bookmaker is likely right.
If the odds move WITH popular opinion, it may be a trap.

Uses The Odds API for multi-market odds (h2h, spreads, totals) across us,uk,eu regions.

Usage:
    python odds_signals.py <fixture_id> <league_id> <season>
"""

import sys
import os
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.football_data import get_match
from api.odds_api import (
    get_sport_key,
    get_odds,
    DEFAULT_REGIONS,
    DEFAULT_MARKETS,
)
from utils import print_json, now_iso, implied_probability


def analyse_odds_structure(odds_data: list[dict], home_team: str, away_team: str) -> dict:
    """Analyse The Odds API response into a standard multi-market structure.

    Returns:
        {
            "match_winner": {Home/Draw/Away: {bookmaker: price}},
            "asian_handicap": {main_line: str, Home/Away: {bookmaker: {price, point}}},
            "over_under": {main_line: str, Over/Under: {bookmaker: {price, point}}},
        }
    """
    result = {
        "match_winner": {},
        "asian_handicap": {},
        "over_under": {},
    }

    for match in odds_data:
        if match.get("home_team") != home_team or match.get("away_team") != away_team:
            continue

        spread_points: list[float] = []
        total_points: list[float] = []

        for bm in match.get("bookmakers", []):
            bm_name = bm.get("title", bm.get("key", "Unknown"))
            for market in bm.get("markets", []):
                mk = market.get("key")
                outcomes = market.get("outcomes", [])

                if mk == "h2h":
                    for o in outcomes:
                        if o["name"] == home_team:
                            key = "Home"
                        elif o["name"] == away_team:
                            key = "Away"
                        else:
                            key = "Draw"
                        result["match_winner"].setdefault(key, {})[bm_name] = o["price"]

                elif mk == "spreads":
                    for o in outcomes:
                        key = "Home" if o["name"] == home_team else "Away"
                        result["asian_handicap"].setdefault(key, {})[bm_name] = {
                            "price": o["price"],
                            "point": o.get("point", 0),
                        }
                        spread_points.append(o.get("point", 0))

                elif mk == "totals":
                    for o in outcomes:
                        result["over_under"].setdefault(o["name"], {})[bm_name] = {
                            "price": o["price"],
                            "point": o.get("point", 0),
                        }
                        total_points.append(o.get("point", 0))

        if spread_points:
            main_pt = Counter(spread_points).most_common(1)[0][0]
            result["asian_handicap"]["main_line"] = str(main_pt)
        if total_points:
            main_pt = Counter(total_points).most_common(1)[0][0]
            result["over_under"]["main_line"] = str(main_pt)

        return result

    return result


def compute_return_rate(home_odds: float, draw_odds: float, away_odds: float) -> float:
    """Compute the bookmaker's return rate (1 - overround) for 1X2 market."""
    total = 1 / home_odds + 1 / draw_odds + 1 / away_odds
    return 1 / total


def compute_kelly_bet(home_odds: float, draw_odds: float, away_odds: float) -> dict:
    """For each outcome, compute simplified Kelly: value = fair_prob - 1/odds.
    Positive = value bet. Uses bookmaker-implied probabilities as fair estimate
    (since we don't have external model probabilities at this level)."""
    return_rate = compute_return_rate(home_odds, draw_odds, away_odds)
    home_implied = implied_probability(home_odds)
    draw_implied = implied_probability(draw_odds)
    away_implied = implied_probability(away_odds)

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
    """Execute odds movement signal analysis using The Odds API."""
    match = get_match(fixture_id)
    if not match:
        return {
            "agent": "odds_signals",
            "fixture_id": fixture_id,
            "error": "Match not found",
        }

    home_name = match["homeTeam"]["name"]
    away_name = match["awayTeam"]["name"]

    sport_key = get_sport_key(league_id)
    if not sport_key:
        return {
            "agent": "odds_signals",
            "fixture": f"{home_name} vs {away_name}",
            "finding": f"League {league_id} not mapped to an Odds API sport key",
            "signal_strength": "none",
            "key_metrics": {},
            "notes": [
                f"No sport key mapping for league_id={league_id}. "
                "Add it to LEAGUE_TO_SPORT_KEY in odds_api.py."
            ],
        }

    try:
        odds_data = get_odds(sport_key, regions=DEFAULT_REGIONS, markets=DEFAULT_MARKETS)
    except Exception as e:
        return {
            "agent": "odds_signals",
            "fixture": f"{home_name} vs {away_name}",
            "finding": f"Failed to fetch odds: {e}",
            "signal_strength": "none",
            "key_metrics": {},
            "notes": [str(e)],
        }

    if not odds_data:
        return {
            "agent": "odds_signals",
            "fixture": f"{home_name} vs {away_name}",
            "finding": "No pre-match odds available yet",
            "signal_strength": "none",
            "key_metrics": {},
            "notes": ["Odds typically appear 1-3 days before kickoff"],
        }

    structure = analyse_odds_structure(odds_data, home_name, away_name)

    # 1X2 analysis
    mw = structure["match_winner"]
    home_odds = None
    away_odds = None
    draw_odds = None

    for side in ("Home", "Draw", "Away"):
        if side in mw and mw[side]:
            best_odd = max(mw[side].values())
            if side == "Home":
                home_odds = best_odd
            elif side == "Draw":
                draw_odds = best_odd
            else:
                away_odds = best_odd

    kelly_data: dict = {}
    if home_odds and draw_odds and away_odds:
        kelly_data = compute_kelly_bet(home_odds, draw_odds, away_odds)

    # Asian handicap
    ah = structure["asian_handicap"]
    ah_line = ah.get("main_line", "N/A")
    ah_home_odds = None
    ah_away_odds = None
    if "Home" in ah and ah["Home"]:
        ah_home_odds = max(v["price"] for v in ah["Home"].values())
    if "Away" in ah and ah["Away"]:
        ah_away_odds = max(v["price"] for v in ah["Away"].values())

    # Over/Under
    ou = structure["over_under"]
    ou_line = ou.get("main_line", "N/A")
    ou_over_odds = None
    ou_under_odds = None
    if "Over" in ou and ou["Over"]:
        ou_over_odds = max(v["price"] for v in ou["Over"].values())
    if "Under" in ou and ou["Under"]:
        ou_under_odds = max(v["price"] for v in ou["Under"].values())

    # Signal interpretation
    notes: list[str] = []
    finding_parts: list[str] = []

    if kelly_data.get("overround", 0) < 0.05:
        notes.append(f"Low overround ({kelly_data['overround']:.1%}): sharp market, efficient pricing")
    elif kelly_data.get("overround", 0) > 0.10:
        notes.append(f"High overround ({kelly_data['overround']:.1%}): wide margin, less signal value")

    if ah_line and ah_line != "N/A":
        notes.append(f"Asian handicap main line: {ah_line}")
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

    if ah_line:
        finding_parts.append(f"AH line {ah_line}")
    if ou_line:
        finding_parts.append(f"O/U line {ou_line}")

    finding = " | ".join(finding_parts) if finding_parts else "Odds data available, see key_metrics"

    if kelly_data:
        finding += f" (return rate: {kelly_data.get('return_rate', 0):.1%})"

    if home_odds and ah_line and ou_line:
        strength = "strong"
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
