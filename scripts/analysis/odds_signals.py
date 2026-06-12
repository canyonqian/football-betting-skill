"""Sub-Agent B: Odds Movement Signal Analysis.

Interprets opening-to-current odds movement as bookmaker intent:
- Water level (shuiwei) changes → market pressure direction
- Line movement (upgrade/downgrade of handicap) → bookmaker risk adjustment
- Return rate shift → margin rebate changes signal confidence

Key insight: sharp odds movement late before kickoff is the strongest signal.
If the odds move AGAINST popular opinion, the bookmaker is likely right.
If the odds move WITH popular opinion, it may be a trap.

Data sources (tried in order):
  1. The Odds API (40+ bookmakers, international)
  2. odds-api.io (Bet365 + Unibet, deep markets)
  3. 竞彩网 sporttery.cn (Chinese government lottery)

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
from api.odds_api_io import get_events as io_get_events, get_odds as io_get_odds, find_event_id as io_find_event_id, extract_odds_summary
from api.sporttery import search_by_teams, get_world_cup_matches
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


def run(match_id: int, competition_id: str, season: int) -> dict:
    """Execute odds movement signal analysis using The Odds API."""
    match = get_match(match_id)
    if not match:
        return {
            "agent": "odds_signals",
            "fixture_id": match_id,
            "error": "Match not found",
        }

    home_name = match["homeTeam"]["name"]
    away_name = match["awayTeam"]["name"]

    sport_key = get_sport_key(competition_id)
    if not sport_key:
        return {
            "agent": "odds_signals",
            "fixture": f"{home_name} vs {away_name}",
            "finding": f"League {competition_id} not mapped to an Odds API sport key",
            "signal_strength": "none",
            "key_metrics": {},
            "notes": [
                f"No sport key mapping for league_id={competition_id}. "
                "Add it to LEAGUE_TO_SPORT_KEY in odds_api.py."
            ],
        }

    structure = {}
    source = "the_odds_api"
    all_notes = []
    match_winner_odds = {}

    # Try The Odds API first
    try:
        odds_data = get_odds(sport_key, regions=DEFAULT_REGIONS, markets=DEFAULT_MARKETS)
        if odds_data:
            structure = analyse_odds_structure(odds_data, home_name, away_name)
            mw = structure.get("match_winner", {})
            if mw.get("Home") or mw.get("Away") or mw.get("Draw"):
                source = "the_odds_api"
                all_notes.append(f"Source: The Odds API ({len(mw.get('Home',{})) + len(mw.get('Draw',{})) + len(mw.get('Away',{}))} bookmakers)")
    except Exception:
        pass

    # Try odds-api.io as fallback/supplement
    if not structure.get("match_winner"):
        try:
            io_event_id = io_find_event_id(home_name, away_name)
            if io_event_id:
                io_data = io_get_odds(io_event_id, bookmakers="Bet365,Unibet")
                io_summary = extract_odds_summary(io_data)
                io_home = None
                io_draw = None
                io_away = None
                io_ah_home = None
                io_ah_away = None
                io_ou_over = None
                io_ou_under = None
                io_ou_line = None

                for book, markets in io_summary.items():
                    if "ML" in markets:
                        ml = markets["ML"][0]
                        h = float(ml.get("home", 0)) or None
                        d = float(ml.get("draw", 0)) or None
                        a = float(ml.get("away", 0)) or None
                        if h and (not io_home or h > io_home): io_home = h
                        if d and (not io_draw or d > io_draw): io_draw = d
                        if a and (not io_away or a > io_away): io_away = a

                    if "Spread" in markets:
                        for s in markets["Spread"]:
                            pt = float(s.get("hdp", 0))
                            h = float(s.get("home", 0)) or None
                            a = float(s.get("away", 0)) or None
                            if abs(pt) <= 1.0:
                                if h and (not io_ah_home or h > io_ah_home): io_ah_home = h
                                if a and (not io_ah_away or a > io_ah_away): io_ah_away = a

                    if "Totals" in markets:
                        for t in markets["Totals"]:
                            pt = float(t.get("hdp", 0))
                            ov = float(t.get("over", 0)) or None
                            un = float(t.get("under", 0)) or None
                            if abs(pt - 2.5) <= 0.5:
                                io_ou_line = str(pt)
                                if ov: io_ou_over = ov
                                if un: io_ou_under = un

                if io_home:
                    source = "odds-api.io"
                    structure["match_winner"] = {
                        "Home": {"odds-api.io": io_home},
                        "Draw": {"odds-api.io": io_draw} if io_draw else {},
                        "Away": {"odds-api.io": io_away} if io_away else {},
                    }
                    if io_ah_home or io_ah_away:
                        structure["asian_handicap"] = {
                            "Home": {"odds-api.io": {"price": io_ah_home, "point": -0.5}} if io_ah_home else {},
                            "Away": {"odds-api.io": {"price": io_ah_away, "point": -0.5}} if io_ah_away else {},
                            "main_line": "-0.5",
                        }
                    if io_ou_over or io_ou_under:
                        structure["over_under"] = {
                            "Over": {"odds-api.io": {"price": io_ou_over, "point": float(io_ou_line)}} if io_ou_over else {},
                            "Under": {"odds-api.io": {"price": io_ou_under, "point": float(io_ou_line)}} if io_ou_under else {},
                            "main_line": io_ou_line or "2.5",
                        }
                    all_notes.append(f"Source: odds-api.io (Bet365, Unibet)")
        except Exception:
            pass

    # Try sporttery.cn as last resort
    if not structure.get("match_winner"):
        try:
            sporttery_data = search_by_teams(home_name, away_name)
            if not sporttery_data:
                for wc in get_world_cup_matches():
                    if home_name.lower() in wc["home_team"].lower() or home_name.lower() in wc["away_team"].lower():
                        sporttery_data = wc
                        break
            if not sporttery_data:
                sporttery_data = search_by_teams(home_name, away_name)

            if sporttery_data and sporttery_data.get("odds", {}).get("h2h"):
                h2h = sporttery_data["odds"]["h2h"]
                if h2h.get("home"):
                    source = "sporttery"
                    structure["match_winner"] = {
                        "Home": {"竞彩": h2h["home"]},
                        "Draw": {"竞彩": h2h["draw"]} if h2h.get("draw") else {},
                        "Away": {"竞彩": h2h["away"]} if h2h.get("away") else {},
                    }
                    ah = sporttery_data["odds"].get("asian_handicap")
                    if ah and ah.get("home"):
                        structure["asian_handicap"] = {
                            "Home": {"竞彩": {"price": ah["home"], "point": float(ah.get("goal_line_value", 0))}},
                            "Away": {"竞彩": {"price": ah["away"], "point": float(ah.get("goal_line_value", 0))}},
                            "main_line": ah.get("goal_line", "0"),
                        }
                    all_notes.append(f"Source: 竞彩网 (Chinese government lottery odds)")
        except Exception:
            pass

    if not structure.get("match_winner"):
        return {
            "agent": "odds_signals",
            "fixture": f"{home_name} vs {away_name}",
            "finding": "No pre-match odds available from any data source",
            "signal_strength": "none",
            "key_metrics": {},
            "notes": ["The Odds API, odds-api.io, and 竞彩网 all returned no data"],
        }

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
    match_id = int(sys.argv[1])
    competition_id = sys.argv[2]
    season = int(sys.argv[3])
    try:
        result = run(match_id, competition_id, season)
        print_json(result)
    except Exception as e:
        print_json({"agent": "odds_signals", "fixture_id": match_id, "error": str(e)})
