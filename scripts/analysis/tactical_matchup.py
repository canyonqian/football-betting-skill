"""Sub-Agent G: Tactical Style Matching Analysis.

Analyses formations, playing style, and tactical compatibility.
Uses football-data.org + soccerdata + web search guidance.

Usage:
    python tactical_matchup.py <match_id> <competition_id> <season>
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.football_data import get_match, get_standings, get_team, get_head2head
from utils import print_json

try:
    from soccerdata import FBref
    HAS_SOCCERDATA = True
except ImportError:
    HAS_SOCCERDATA = False

FORMATION_COUNTERS = {
    "3-5-2": ["4-3-3", "4-2-3-1", "4-4-2"],
    "3-4-3": ["4-3-3", "4-2-3-1"],
    "4-3-3": ["4-4-2", "4-4-1-1"],
    "4-2-3-1": ["4-3-3", "4-4-2"],
    "4-4-2": ["3-5-2", "3-4-3"],
    "3-4-2-1": ["4-4-2", "4-3-3"],
    "5-3-2": ["4-3-3", "4-2-3-1"],
    "5-4-1": ["4-3-3", "4-2-3-1"],
}

COMP_TO_FBREF = {
    "PL": "ENG-Premier League", "BL1": "GER-Bundesliga",
    "SA": "ITA-Serie A", "PD": "ESP-La Liga",
    "FL1": "FRA-Ligue 1", "CL": "UEFA-Champions League",
}


def get_style_from_fbref(competition_id: str, season: int) -> dict:
    """Get per-game stats from FBref via soccerdata."""
    if not HAS_SOCCERDATA:
        return {"available": False, "note": "soccerdata not installed"}
    league = COMP_TO_FBREF.get(competition_id)
    if not league:
        return {"available": False, "note": f"Competition {competition_id} not in FBref"}
    try:
        fbref = FBref(league, str(season))
        schedule = fbref.read_schedule()
        if schedule is not None and not schedule.empty:
            return {"available": True, "matches": len(schedule)}
        return {"available": True, "matches": 0}
    except Exception as e:
        return {"available": False, "note": str(e)[:100]}


def get_league_position(standings: list, team_id: int) -> int:
    """Find a team's league position from standings data."""
    for entry in standings:
        for row in entry.get("table", []):
            if row.get("team", {}).get("id") == team_id:
                return row.get("position", 0)
    return 0


def classify_style(team_data: dict, league_pos: int) -> dict:
    """Classify team style from available data (no API-Football stats)."""
    tags = []
    coach = team_data.get("coach", {})
    squad = team_data.get("squad", [])
    squad_size = len(squad)

    if league_pos <= 4:
        tags.append("top-tier")
    elif league_pos >= 15:
        tags.append("struggling")
    else:
        tags.append("mid-table")

    if squad_size >= 28:
        tags.append("deep-squad")
    elif squad_size <= 22:
        tags.append("thin-squad")

    return {
        "league_position": league_pos,
        "squad_size": squad_size,
        "coach_name": coach.get("name", "Unknown") if coach else "Unknown",
        "style_tags": tags,
    }


def compute_clash(home_info: dict, away_info: dict, home_form: str, away_form: str,
                  formation_notes: list) -> dict:
    """Compute tactical compatibility."""
    clashes = []
    advantages = []

    home_pos = home_info.get("league_position", 10)
    away_pos = away_info.get("league_position", 10)

    if home_pos <= 4 and away_pos >= 15:
        advantages.append(f"{home_info.get('coach_name')} top-4 side vs struggling {away_info.get('coach_name')}")
    if away_pos <= 4 and home_pos >= 15:
        advantages.append(f"{away_info.get('coach_name')} top-4 side vs struggling {home_info.get('coach_name')}")

    if home_info.get("squad_size", 0) >= 28:
        advantages.append(f"Deep home squad ({home_info['squad_size']} players) — rotation advantage")
    if away_info.get("squad_size", 0) >= 28:
        advantages.append(f"Deep away squad ({away_info['squad_size']} players) — rotation advantage")

    # Strong form vs weak form
    if home_form and away_form:
        h_wins = home_form.count("W") / max(len(home_form), 1) if home_form else 0
        a_wins = away_form.count("W") / max(len(away_form), 1) if away_form else 0
        if h_wins > a_wins + 0.3:
            advantages.append(f"Home in significantly better form ({h_wins:.0%} vs {a_wins:.0%})")
        if a_wins > h_wins + 0.3:
            advantages.append(f"Away in significantly better form ({a_wins:.0%} vs {h_wins:.0%})")

    return {
        "key_clashes": clashes,
        "tactical_advantages": advantages + formation_notes,
        "clash_count": len(clashes),
        "advantage_count": len(advantages) + len(formation_notes),
    }


def run(match_id: int, competition_id: str, season: int) -> dict:
    match = get_match(match_id)
    if not match:
        return {"agent": "tactical_matchup", "match_id": match_id, "error": "Match not found"}

    home_name = match["homeTeam"]["name"]
    away_name = match["awayTeam"]["name"]
    home_id = match["homeTeam"]["id"]
    away_id = match["awayTeam"]["id"]

    # Team info (squad, coach)
    home_team = get_team(home_id) or {}
    away_team = get_team(away_id) or {}

    # Standings
    standings = get_standings(competition_id)
    home_pos = get_league_position(standings, home_id)
    away_pos = get_league_position(standings, away_id)

    # Style classification
    home_style = classify_style(home_team, home_pos)
    away_style = classify_style(away_team, away_pos)

    # Form from team data
    home_form = home_team.get("form", "")
    away_form = away_team.get("form", "")

    # H2H context
    try:
        h2h = get_head2head(match_id)
        h2h_count = len(h2h.get("matches", [])) if isinstance(h2h, dict) else len(h2h) if isinstance(h2h, list) else 0
    except Exception:
        h2h_count = 0

    # Formation analysis via web search (can't get from football-data.org)
    formation_notes = [f"Formations not available from football-data.org. Web search flashscore.com for {home_name} vs {away_name} lineups."]

    # Soccerdata stats
    fbref_data = get_style_from_fbref(competition_id, season)

    # Clash analysis
    clash = compute_clash(home_style, away_style, home_form, away_form, formation_notes)

    notes = []
    if fbref_data.get("available"):
        notes.append(f"FBref stats available ({fbref_data.get('matches', '?')} matches)")
    else:
        notes.append(f"FBref: {fbref_data.get('note', 'not available')}. Web search sofascore.com for player stats.")
    notes.append(f"H2H encounters: {h2h_count}")
    notes.extend(clash.get("tactical_advantages", []))

    finding_parts = []
    if clash.get("advantage_count", 0) > 0:
        finding_parts.append(f"{clash['advantage_count']} tactical advantage(s) identified")
    if h2h_count > 5:
        finding_parts.append(f"{h2h_count} H2H meetings available for context")
    finding = " | ".join(finding_parts) if finding_parts else "Tactical styles assessed"

    strength = "medium" if clash.get("advantage_count", 0) >= 2 else "weak"

    return {
        "agent": "tactical_matchup",
        "fixture": f"{home_name} vs {away_name}",
        "finding": finding,
        "signal_strength": strength,
        "key_metrics": {
            "home": home_style,
            "away": away_style,
            "style_clash": clash,
            "soccerdata": fbref_data,
            "h2h_count": h2h_count,
        },
        "notes": notes,
        "search_queries": [
            f"{home_name} vs {away_name} predicted lineup formation",
            f"{home_name} recent results form guide",
            f"{away_name} recent results form guide",
        ],
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print_json({"error": "Usage: tactical_matchup.py <match_id> <competition_id> <season>"})
        sys.exit(1)
    match_id = int(sys.argv[1])
    competition_id = sys.argv[2]
    season = int(sys.argv[3])
    try:
        result = run(match_id, competition_id, season)
        print_json(result)
    except Exception as e:
        print_json({"agent": "tactical_matchup", "match_id": match_id, "error": str(e)})
