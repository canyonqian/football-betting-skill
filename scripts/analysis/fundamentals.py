"""Sub-Agent A: Fundamentals vs Odds Gap Analysis.

Uses football-data.org v4 for match data, H2H, standings, and form.
Compares fundamentals-based probabilities against market odds from The Odds API.

Usage:
    python fundamentals.py <match_id> <competition_id> <season>

Output: JSON to stdout following sub-agent output contract.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone, timedelta

from api.football_data import (
    get_match,
    get_matches,
    get_head2head,
    get_standings,
)
from api.odds_api import get_odds, extract_h2h_odds
from utils import print_json, now_iso, implied_probability

COMPETITION_TO_SPORT_KEY = {
    "PL": "soccer_epl",
    "PD": "soccer_spain_la_liga",
    "BL1": "soccer_germany_bundesliga",
    "SA": "soccer_italy_serie_a",
    "FL1": "soccer_france_ligue_one",
    "CL": "soccer_uefa_champs_league",
    "EL": "soccer_uefa_europa_league",
    "EC": "soccer_uefa_european_championship",
    "DED": "soccer_netherlands_eredivisie",
    "PPL": "soccer_portugal_primeira_liga",
    "BSA": "soccer_brazil_campeonato",
    "MLS": "soccer_usa_mls",
}


def _parse_date(iso_str: str) -> datetime:
    if not iso_str:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _form_score(form_str: str, last_n: int = 10) -> float:
    if not form_str:
        return 0.5
    chars = form_str.replace(",", "").replace(" ", "")[:last_n]
    if not chars:
        return 0.5
    wins = chars.count("W")
    return wins / len(chars)


def _find_in_table(table: list[dict], team_id: int) -> dict:
    for row in table:
        if row.get("team", {}).get("id") == team_id:
            return row
    return {}


def _season_date_range(season: int) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    date_to = now.strftime("%Y-%m-%d")
    date_from = f"{season}-07-01"
    return date_from, date_to


def run(match_id: int, competition_id: str, season: int) -> dict:
    # 1. Match detail
    match = get_match(match_id)
    if not match:
        return {
            "agent": "fundamentals",
            "fixture": "",
            "error": f"Match {match_id} not found",
        }

    home = match.get("homeTeam", {})
    away = match.get("awayTeam", {})
    home_id = home.get("id")
    away_id = away.get("id")
    home_name = home.get("name", "") or home.get("shortName", "") or str(home_id)
    away_name = away.get("name", "") or away.get("shortName", "") or str(away_id)
    fixture_date = match.get("utcDate", "")

    # 2. H2H history
    h2h_data = get_head2head(match_id)
    h2h_matches = h2h_data.get("matches", [])

    # 3. League standings
    standings_list = get_standings(competition_id, season=season)
    standings_table = []
    for s in standings_list:
        if s.get("type") == "TOTAL":
            standings_table = s.get("table", [])
            break
    if not standings_table and standings_list:
        standings_table = standings_list[0].get("table", [])

    home_standings = _find_in_table(standings_table, home_id)
    away_standings = _find_in_table(standings_table, away_id)

    # 4. Recent finished matches for home/away GPG
    date_from, date_to = _season_date_range(season)
    recent = get_matches(
        competition_id,
        date_from=date_from,
        date_to=date_to,
        status="FINISHED",
    )

    home_goals_home = 0
    home_played_home = 0
    away_goals_away = 0
    away_played_away = 0

    for m in recent:
        ht = m.get("homeTeam", {})
        at = m.get("awayTeam", {})
        score = m.get("score", {}).get("fullTime", {})
        hg = score.get("home") or 0
        ag = score.get("away") or 0

        if ht.get("id") == home_id:
            home_goals_home += hg
            home_played_home += 1
        if at.get("id") == away_id:
            away_goals_away += ag
            away_played_away += 1

    home_gpg_home = home_goals_home / max(home_played_home, 1)
    away_gpg_away = away_goals_away / max(away_played_away, 1)

    # 5. Market odds from The Odds API
    sport_key = COMPETITION_TO_SPORT_KEY.get(competition_id)
    market_home_odds = None
    if sport_key:
        try:
            odds_data = get_odds(sport_key)
            odds_result = extract_h2h_odds(odds_data, home_name, away_name)
            if odds_result:
                first_bm = next(iter(odds_result.values()))
                market_home_odds = first_bm.get(home_name)
        except Exception:
            pass

    # --- Compute fundamentals-based expectation ---

    home_form_str = home_standings.get("form", "")
    away_form_str = away_standings.get("form", "")
    home_form_score_val = _form_score(home_form_str)
    away_form_score_val = _form_score(away_form_str)

    # H2H win rate as home team
    h2h_home_wins = 0
    h2h_total = len(h2h_matches)
    for h in h2h_matches:
        ht_id = h.get("homeTeam", {}).get("id")
        winner = h.get("score", {}).get("winner")
        if ht_id == home_id and winner == "HOME_TEAM":
            h2h_home_wins += 1
        elif ht_id == away_id and winner == "AWAY_TEAM":
            h2h_home_wins += 1
    h2h_home_win_rate = h2h_home_wins / max(h2h_total, 1)

    # Composite fundamentals expectation (home win probability)
    goals_ratio = home_gpg_home / max(home_gpg_home + away_gpg_away, 0.01)

    home_strength = (
        home_form_score_val * 0.35 +
        goals_ratio * 0.30 +
        h2h_home_win_rate * 0.20 +
        0.15
    )
    away_strength = (
        away_form_score_val * 0.35 +
        (1 - goals_ratio) * 0.30 +
        (1 - h2h_home_win_rate) * 0.20
    )

    total = home_strength + away_strength
    fair_home_prob = home_strength / max(total, 0.01)

    # --- Compare to market odds ---
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
            "fixture_date": fixture_date,
            "fair_home_probability": round(fair_home_prob, 3),
            "market_implied_probability": round(market_implied, 3) if market_implied else None,
            "gap": round(gap, 3) if gap else None,
            "home_form_score": round(home_form_score_val, 3),
            "away_form_score": round(away_form_score_val, 3),
            "home_gpg_home": round(home_gpg_home, 2),
            "away_gpg_away": round(away_gpg_away, 2),
            "h2h_home_win_rate": round(h2h_home_win_rate, 3),
            "h2h_total_matches": h2h_total,
        },
        "notes": notes,
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print_json({"error": "Usage: fundamentals.py <match_id> <competition_id> <season>"})
        sys.exit(1)
    match_id = int(sys.argv[1])
    competition_id = sys.argv[2]
    season = int(sys.argv[3])
    try:
        result = run(match_id, competition_id, season)
        print_json(result)
    except Exception as e:
        print_json({"agent": "fundamentals", "fixture_id": match_id, "error": str(e)})
