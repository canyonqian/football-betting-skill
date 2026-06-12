"""Sub-Agent D: Multi-Bookmaker Divergence Analysis (The Odds API).

Compares odds across 40+ bookmakers to detect:
- Divergence: high dispersion among bookmakers = uncertainty, low confidence
- Outliers: a bookmaker significantly different from consensus = possible edge
- Sharp vs retail: Pinnacle/Betfair (sharp) vs retail bookmakers

The bigger the disagreement among bookmakers, the less reliable the odds signal.
When sharp bookmakers disagree with retail bookmakers, follow the sharps.

Usage:
    python bookmaker_divergence.py <fixture_id> <league_id> <season>
"""

import sys
import os
import statistics
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.api_football import get_fixture_by_id
from api.odds_api import (
    get_sport_key,
    get_odds,
    extract_h2h_odds,
    extract_spreads,
    extract_totals,
)
from utils import print_json

# Sharp bookmakers — historically most efficient, market-leading prices
SHARP_BOOKMAKERS = {"Pinnacle", "Betfair", "Matchbook", "Marathonbet", "1xBet", "Paddy Power"}

# Retail bookmakers — recreational money, wider margins
RETAIL_BOOKMAKERS = {"Bet365", "William Hill", "Unibet", "Ladbrokes", "BetVictor",
                     "DraftKings", "FanDuel", "BetMGM"}


def collapse_to_prices(odds_by_bookmaker: dict) -> dict:
    """Flatten spread/total {bm: {outcome: {price, point}}} to {bm: {outcome_key: price}}."""
    result = {}
    for bm_name, outcomes in odds_by_bookmaker.items():
        for outcome_name, data in outcomes.items():
            if isinstance(data, dict):
                key = f"{outcome_name}@{data['point']}"
                result.setdefault(bm_name, {})[key] = data["price"]
            else:
                result.setdefault(bm_name, {})[outcome_name] = data
    return result


def compute_divergence(odds_by_bookmaker: dict[str, dict]) -> dict:
    """Compute odds dispersion statistics across bookmakers for each outcome.

    Returns {outcome: {mean, median, std, min, max, count, sharp_mean, retail_mean}}
    """
    result = {}

    all_outcomes = set()
    for bm_odds in odds_by_bookmaker.values():
        all_outcomes.update(bm_odds.keys())

    for outcome in sorted(all_outcomes):
        values = []
        sharp_values = []
        retail_values = []

        for bm_name, bm_odds in odds_by_bookmaker.items():
            if outcome in bm_odds:
                values.append(bm_odds[outcome])
                if bm_name in SHARP_BOOKMAKERS:
                    sharp_values.append(bm_odds[outcome])
                if bm_name in RETAIL_BOOKMAKERS:
                    retail_values.append(bm_odds[outcome])

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
                "retail_mean": round(statistics.mean(retail_values), 2) if retail_values else None,
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
                "retail_mean": round(values[0], 2) if retail_values else None,
            }

    return result


def analyse_divergence_level(divergence_data: dict) -> tuple[str, list[str]]:
    """Classify divergence level and generate interpretation."""
    if not divergence_data:
        return "none", ["No bookmaker data available"]

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
        sharp_m = stats.get("sharp_mean")
        market_m = stats.get("mean")
        if sharp_m and market_m:
            gap = sharp_m - market_m
            if abs(gap) >= 0.05:
                direction = "higher" if gap > 0 else "lower"
                notes.append(
                    f"Sharp bookmakers {direction} on '{outcome}' "
                    f"(sharp: {sharp_m}, market avg: {market_m})"
                )
        retail_m = stats.get("retail_mean")
        if sharp_m and retail_m:
            gap_sr = sharp_m - retail_m
            if abs(gap_sr) >= 0.05:
                direction = "above" if gap_sr > 0 else "below"
                notes.append(
                    f"Sharp-vs-retail gap on '{outcome}': sharps {direction} retail "
                    f"(sharp: {sharp_m}, retail: {retail_m})"
                )

    return level, notes


def run(fixture_id: int, league_id: int, season: int) -> dict:
    """Execute multi-bookmaker divergence analysis using The Odds API."""
    fixture = get_fixture_by_id(fixture_id)
    if not fixture:
        return {"agent": "bookmaker_divergence", "fixture_id": fixture_id,
                "error": "Fixture not found"}

    f = fixture[0]
    home_name = f["teams"]["home"]["name"]
    away_name = f["teams"]["away"]["name"]

    sport_key = get_sport_key(league_id)
    if not sport_key:
        return {
            "agent": "bookmaker_divergence",
            "fixture": f"{home_name} vs {away_name}",
            "error": f"Unknown league_id {league_id} — add mapping to LEAGUE_TO_SPORT_KEY in odds_api.py",
        }

    odds_data = get_odds(sport_key)

    h2h_odds = extract_h2h_odds(odds_data, home_name, away_name)
    spread_odds = extract_spreads(odds_data, home_name, away_name)
    total_odds = extract_totals(odds_data, home_name, away_name)

    if not h2h_odds and not spread_odds and not total_odds:
        return {
            "agent": "bookmaker_divergence",
            "fixture": f"{home_name} vs {away_name}",
            "finding": "No odds data available",
            "signal_strength": "none",
            "key_metrics": {},
            "notes": ["Odds not yet published for this fixture on The Odds API"],
        }

    h2h_div = compute_divergence(h2h_odds)
    spread_div = compute_divergence(collapse_to_prices(spread_odds))
    total_div = compute_divergence(collapse_to_prices(total_odds))

    h2h_level, h2h_notes = analyse_divergence_level(h2h_div)
    spread_level, spread_notes = analyse_divergence_level(spread_div)
    total_level, total_notes = analyse_divergence_level(total_div)

    all_notes = h2h_notes + spread_notes + total_notes

    total_bookmakers = len(set(
        list(h2h_odds.keys()) + list(spread_odds.keys()) + list(total_odds.keys())
    ))
    sharp_count = sum(1 for bm in {*h2h_odds, *spread_odds, *total_odds} if bm in SHARP_BOOKMAKERS)
    retail_count = sum(1 for bm in {*h2h_odds, *spread_odds, *total_odds} if bm in RETAIL_BOOKMAKERS)

    finding = f"{total_bookmakers} bookmakers via The Odds API ({sharp_count} sharp, {retail_count} retail)"
    if h2h_level in ("very_low", "low"):
        finding += " — strong consensus"
    elif h2h_level == "high":
        finding += " — high divergence, signals unreliable"
    else:
        finding += " — moderate agreement"

    return {
        "agent": "bookmaker_divergence",
        "source": "the_odds_api",
        "sport_key": sport_key,
        "fixture": f"{home_name} vs {away_name}",
        "finding": finding,
        "signal_strength": "strong" if h2h_level in ("very_low", "low")
                          else "medium" if h2h_level == "medium"
                          else "weak",
        "key_metrics": {
            "bookmaker_count": total_bookmakers,
            "sharp_bookmaker_count": sharp_count,
            "retail_bookmaker_count": retail_count,
            "match_winner_divergence": {
                "level": h2h_level,
                "details": h2h_div,
            },
            "asian_handicap_divergence": {
                "level": spread_level,
                "details": spread_div,
            },
            "over_under_divergence": {
                "level": total_level,
                "details": total_div,
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
