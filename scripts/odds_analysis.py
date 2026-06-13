"""Odds Analysis — comprehensive sporttery (竞彩) all-markets extraction.

For a given match, extracts ALL available bet types with odds,
computes fair probabilities (overround-adjusted), and produces
market signal interpretation.

No API keys required. Uses public sporttery.cn endpoint.

Bet types:
  1. HAD  (胜平负)       — 1X2 match result
  2. HHAD (让球胜平负)   — Asian handicap 3-way (让胜/让平/让负)
  3. CRS  (比分)         — correct score (all 31 scores)
  4. HAFU (半全场)       — HT/FT double (9 combos)
  5. TTG  (总进球数)     — total goals (0,1,2,3,4,5,6,7+)

Usage:
    python odds_analysis.py "Brazil" "Morocco"

Output: JSON with all markets, probabilities, and market signals.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from api.sporttery import search_by_teams, get_raw_match
from utils import print_json


def overround_adjust(odds_dict: dict[str, float]) -> dict[str, float]:
    """Remove bookmaker overround from odds to get fair probabilities."""
    total = sum(1.0 / o for o in odds_dict.values() if o > 0)
    if total <= 0:
        return {}
    return {k: (1.0 / v) / total for k, v in odds_dict.items() if v > 0}


def analyse_had(data: dict) -> dict:
    """1X2 (胜平负) analysis."""
    h2h = data.get("h2h")
    if not h2h:
        return {"available": False}
    home = h2h.get("home")
    draw = h2h.get("draw")
    away = h2h.get("away")
    if not home or not draw or not away:
        return {"available": False}

    raw = {"home": home, "draw": draw, "away": away}
    fair = overround_adjust(raw)
    return {
        "available": True,
        "odds": raw,
        "fair_probability": {k: round(v, 4) for k, v in fair.items()},
        "overround": round(1 - (1.0 / sum(1.0 / v for v in raw.values())), 4),
        "updated": h2h.get("updated", ""),
        "prediction": max(fair, key=fair.get) if fair else "",
    }


def analyse_hhad(data: dict) -> dict:
    """Asian handicap 3-way (让球盘) analysis."""
    hhad = data.get("asian_handicap")
    if not hhad or not hhad.get("home"):
        return {"available": False}

    home = hhad["home"]
    draw = hhad.get("draw")
    away = hhad["away"]
    line = hhad.get("goal_line", "")
    line_val = hhad.get("goal_line_value", "")

    result = {
        "available": True,
        "line": line,
        "line_value": line_val,
        "updated": hhad.get("updated", ""),
    }

    if draw and away:
        raw = {"handicap_home": home, "handicap_draw": draw, "handicap_away": away}
        fair = overround_adjust(raw)
        result["odds"] = raw
        result["fair_probability"] = {k: round(v, 4) for k, v in fair.items()}
        result["overround"] = round(1 - (1.0 / sum(1.0 / v for v in raw.values())), 4)
        result["prediction"] = max(fair, key=fair.get) if fair else ""
    else:
        result["odds"] = {"handicap_home": home, "handicap_away": away}
    return result


def analyse_crs(data: dict) -> dict:
    """Correct score (比分) analysis."""
    crs = data.get("correct_score")
    if not crs or not crs.get("scores"):
        return {"available": False}

    scores = crs.get("scores", {})
    odds = {s: v for s, v in scores.items()}

    if not odds:
        return {"available": False}

    # Compute fair probabilities (overround-adjusted)
    fair = overround_adjust(odds)
    sorted_fair = sorted(fair.items(), key=lambda x: x[1], reverse=True)

    return {
        "available": True,
        "total_outcomes": len(odds),
        "overround": round(1 - (1.0 / sum(1.0 / v for v in odds.values())), 4),
        "updated": crs.get("updated", ""),
        "top_5_scores": [
            {"score": s, "odds": round(odds[s], 2), "fair_probability": round(fair.get(s, 0), 4)}
            for s, _ in sorted_fair[:5]
        ],
        "most_likely": {
            "score": sorted_fair[0][0],
            "odds": round(odds[sorted_fair[0][0]], 2),
            "fair_probability": round(sorted_fair[0][1], 4),
        } if sorted_fair else {},
        "all_scores": [
            {"score": s, "odds": round(v, 2), "fair_probability": round(fair.get(s, 0), 4)}
            for s, v in sorted(odds.items(), key=lambda x: x[1])
        ],
    }


def analyse_hafu(data: dict) -> dict:
    """Half-time/Full-time (半全场) analysis."""
    hafu = data.get("half_time_full_time")
    if not hafu or not hafu.get("odds"):
        return {"available": False}

    odds = hafu["odds"]
    fair = overround_adjust(odds)
    sorted_fair = sorted(fair.items(), key=lambda x: x[1], reverse=True)

    return {
        "available": True,
        "odds": odds,
        "fair_probability": {k: round(v, 4) for k, v in fair.items()},
        "overround": round(1 - (1.0 / sum(1.0 / v for v in odds.values())), 4),
        "updated": hafu.get("updated", ""),
        "top_3": [{"outcome": k, "odds": round(odds[k], 2), "fair_probability": round(v, 4)}
                  for k, v in sorted_fair[:3]],
        "prediction": sorted_fair[0][0] if sorted_fair else "",
    }


def analyse_ttg(data: dict) -> dict:
    """Total goals (总进球数) analysis."""
    ttg = data.get("total_goals")
    if not ttg or not ttg.get("goals"):
        return {"available": False}

    goals = ttg["goals"]
    odds = {k: v["odds"] for k, v in goals.items()}
    fair = overround_adjust(odds)

    # Separate over/under 2.5
    over_keys = ["3", "4", "5", "6", "7+"]
    under_keys = ["0", "1", "2"]
    over_prob = sum(fair.get(k, 0) for k in over_keys)
    under_prob = sum(fair.get(k, 0) for k in under_keys)

    sorted_fair = sorted(fair.items(), key=lambda x: x[1], reverse=True)

    return {
        "available": True,
        "odds": {k: round(v["odds"], 2) for k, v in goals.items()},
        "trends": {k: v["trend"] for k, v in goals.items() if v.get("trend")},
        "fair_probability": {k: round(v, 4) for k, v in fair.items()},
        "overround": round(1 - (1.0 / sum(1.0 / v for v in odds.values())), 4),
        "updated": ttg.get("updated", ""),
        "over_2_5_probability": round(over_prob, 4),
        "under_2_5_probability": round(under_prob, 4),
        "most_likely": sorted_fair[0][0] if sorted_fair else "",
    }


def analyse_odds_list(raw_match: dict) -> dict:
    """Extract odds from oddsList if available (richer than top-level fields)."""
    odds_list = raw_match.get("oddsList", [])
    if not odds_list:
        return {}

    result = {}
    for entry in odds_list:
        code = entry.get("poolCode", "")
        if code == "HAD":
            result["had_oddslist"] = {
                "home": float(entry.get("h", 0)) if entry.get("h") else None,
                "draw": float(entry.get("d", 0)) if entry.get("d") else None,
                "away": float(entry.get("a", 0)) if entry.get("a") else None,
                "updated": f"{entry.get('updateDate', '')} {entry.get('updateTime', '')}",
            }
        elif code == "HHAD":
            result["hhad_oddslist"] = {
                "home": float(entry.get("h", 0)) if entry.get("h") else None,
                "draw": float(entry.get("d", 0)) if entry.get("d") else None,
                "away": float(entry.get("a", 0)) if entry.get("a") else None,
                "goal_line": entry.get("goalLine", ""),
                "goal_line_value": entry.get("goalLineValue", ""),
                "updated": f"{entry.get('updateDate', '')} {entry.get('updateTime', '')}",
            }

    return result


def run(home_team: str, away_team: str) -> dict:
    """Execute comprehensive odds analysis for a match."""
    # Try parsed data first
    parsed = search_by_teams(home_team, away_team)
    raw = get_raw_match(home_team, away_team)

    if not parsed and not raw:
        return {"error": f"Match not found in sporttery: {home_team} vs {away_team}"}

    if not parsed:
        return {"error": "Match found but parsing failed"}

    match_info = {
        "match_num": parsed.get("match_num", ""),
        "home_team": parsed.get("home_team", ""),
        "away_team": parsed.get("away_team", ""),
        "home_rank": parsed.get("home_rank", ""),
        "away_rank": parsed.get("away_rank", ""),
        "match_date": parsed.get("match_date", ""),
        "match_time": parsed.get("match_time", ""),
        "league": parsed.get("league", {}).get("full_name", ""),
    }

    odds_data = parsed.get("odds", {})

    # Analyse all markets
    had = analyse_had(odds_data)
    hhad = analyse_hhad(odds_data)
    crs = analyse_crs(odds_data)
    hafu = analyse_hafu(odds_data)
    ttg = analyse_ttg(odds_data)

    # oddsList enrichment
    oddslist = analyse_odds_list(raw) if raw else {}

    # Build market signals summary
    signals = []
    if had.get("available"):
        p = had["prediction"]
        fp = had["fair_probability"].get(p, 0)
        signals.append(f"HAD: {p} ({fp*100:.1f}%)")
    if hhad.get("available") and hhad.get("prediction"):
        p = hhad["prediction"]
        fp = hhad["fair_probability"].get(p, 0)
        signals.append(f"HHAD[{hhad.get('line')}]: {p} ({fp*100:.1f}%)")
    if hafu.get("available"):
        signals.append(f"HAFU: {hafu['prediction']} ({hafu['fair_probability'].get(hafu['prediction'],0)*100:.1f}%)")
    if ttg.get("available"):
        signals.append(f"TTG: most likely {ttg['most_likely']} goals | O2.5={ttg['over_2_5_probability']*100:.1f}% U2.5={ttg['under_2_5_probability']*100:.1f}%")
    if crs.get("available"):
        signals.append(f"CRS: most likely {crs['most_likely']['score']} ({crs['most_likely']['fair_probability']*100:.1f}%)")

    return {
        "match": match_info,
        "markets": {
            "had": had,
            "hhad": hhad,
            "correct_score": crs,
            "half_time_full_time": hafu,
            "total_goals": ttg,
        },
        "oddslist": oddslist,
        "signals": signals,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print_json({"error": "Usage: odds_analysis.py <home_team> <away_team>"})
        sys.exit(1)
    try:
        result = run(sys.argv[1], sys.argv[2])
        print_json(result)
    except Exception as e:
        print_json({"error": str(e)})
