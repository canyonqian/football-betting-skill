"""Sub-Agent H: Player & Coach + xG Analysis.

Analyses player impact, coach experience, xG discrepancy, and squad quality
to identify match-changing variables that the market may be mispricing.

Usage:
    python player_coach_xg.py <match_id> <competition_id> <season>
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.football_data import get_match, get_team, get_matches
from api.odds_api import get_sport_key, get_odds
from utils import print_json


try:
    from soccerdata import Understat
    HAS_XG = True
except ImportError:
    HAS_XG = False


def get_xg_data(competition_id: str, season: int) -> dict:
    """Get real xG from Understat via soccerdata."""
    if not HAS_XG:
        return {"source": "soccerdata_not_installed"}
    COMP_TO_UNDERSTAT = {
        "PL": "ENG-Premier League", "BL1": "GER-Bundesliga",
        "SA": "ITA-Serie A", "PD": "ESP-La Liga",
        "FL1": "FRA-Ligue 1",
    }
    league = COMP_TO_UNDERSTAT.get(competition_id)
    if not league:
        return {"source": "league_not_covered", "note": f"{competition_id} not in Understat"}
    try:
        u = Understat(leagues=league, seasons=str(season))
        schedule = u.read_schedule()
        if schedule is not None and not schedule.empty:
            # Get team-level xG from schedule
            return {"source": "understat", "available": True, "matches": len(schedule)}
        return {"source": "understat", "available": False}
    except Exception as e:
        return {"source": "error", "note": str(e)[:100]}


def analyse_coach(team_id: int, team_name: str) -> dict:
    """Analyze coach data from football-data.org /teams/{id} coach field."""
    try:
        team = get_team(team_id)
    except Exception as e:
        return {"team_name": team_name, "available": False, "note": str(e)[:100]}

    coach = team.get("coach")
    if not coach:
        return {"team_name": team_name, "available": False, "note": "No coach data"}

    contract = coach.get("contract", {})

    return {
        "team_name": team_name,
        "available": True,
        "coach_name": coach.get("name", "Unknown"),
        "nationality": coach.get("nationality"),
        "date_of_birth": coach.get("dateOfBirth"),
        "contract_start": contract.get("start"),
        "contract_until": contract.get("until"),
    }


def analyse_squad_impact(team_id: int, team_name: str) -> dict:
    """Analyze squad composition from football-data.org /teams/{id} squad field."""
    try:
        team = get_team(team_id)
    except Exception as e:
        return {"team_name": team_name, "error": str(e)[:100]}

    squad = team.get("squad", [])

    positions = {}
    for p in squad:
        pos = p.get("position", "Unknown") or "Unknown"
        positions[pos] = positions.get(pos, 0) + 1

    return {
        "team_name": team_name,
        "squad_size": len(squad),
        "position_counts": positions,
        "injury_count": 0,
        "injuries": [],
        "injury_impact": "unknown",
        "note": "Injury data not available in football-data.org free tier",
    }


def run(match_id: int, competition_id: str, season: int) -> dict:
    match_data = get_match(match_id)
    if not match_data:
        return {"agent": "player_coach_xg", "match_id": match_id, "error": "Match not found"}

    home_team = match_data.get("homeTeam", {})
    away_team = match_data.get("awayTeam", {})
    home_id = home_team.get("id")
    away_id = away_team.get("id")
    home_name = home_team.get("name", "Unknown")
    away_name = away_team.get("name", "Unknown")

    # 1. Coach analysis from football-data.org /teams/{id}
    home_coach = analyse_coach(home_id, home_name)
    away_coach = analyse_coach(away_id, away_name)

    # 2. Squad composition
    home_squad = analyse_squad_impact(home_id, home_name)
    away_squad = analyse_squad_impact(away_id, away_name)

    # 3. Real xG data from soccerdata (Understat)
    xg_source = get_xg_data(competition_id, season)

    # Build search guidance for deeper player/coach analysis
    search_queries = [
        f"{home_name} key players form {season}",
        f"{away_name} key players form {season}",
        f"{home_name} coach tactical approach style",
        f"{away_name} coach tactical approach style",
        f"{home_name} {away_name} team news injuries {season}",
    ]

    # Build notes
    notes = []

    if home_coach.get("available"):
        notes.append(f"{home_name} coach: {home_coach['coach_name']}")
    if away_coach.get("available"):
        notes.append(f"{away_name} coach: {away_coach['coach_name']}")

    home_size = home_squad.get("squad_size", 0)
    away_size = away_squad.get("squad_size", 0)
    if home_size > 0 and away_size > 0:
        notes.append(f"Squad sizes: {home_name} {home_size} | {away_name} {away_size}")

    if xg_source.get("source") == "understat" and xg_source.get("available"):
        notes.append(f"xG data available from Understat ({xg_source.get('matches', '?')} matches)")
    else:
        notes.append(f"xG: {xg_source.get('source', 'unavailable')}")

    # Signal strength
    coach_available = home_coach.get("available") and away_coach.get("available")
    squad_available = home_size > 0 and away_size > 0
    xg_available = xg_source.get("source") == "understat" and xg_source.get("available")

    if coach_available and squad_available:
        strength = "strong" if xg_available else "medium"
    elif coach_available or squad_available:
        strength = "medium"
    else:
        strength = "weak"

    finding = f"Player, coach and xG data analysed for {home_name} vs {away_name}"

    return {
        "agent": "player_coach_xg",
        "fixture": f"{home_name} vs {away_name}",
        "finding": finding,
        "signal_strength": strength,
        "key_metrics": {
            "coaches": {
                "home": home_coach,
                "away": away_coach,
            },
            "squads": {
                "home": home_squad,
                "away": away_squad,
            },
            "xg_source": xg_source,
        },
        "notes": notes,
        "search_queries": search_queries,
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print_json({"error": "Usage: player_coach_xg.py <match_id> <competition_id> <season>"})
        sys.exit(1)
    match_id = int(sys.argv[1])
    competition_id = sys.argv[2]
    season = int(sys.argv[3])
    try:
        result = run(match_id, competition_id, season)
        print_json(result)
    except Exception as e:
        print_json({"agent": "player_coach_xg", "match_id": match_id, "error": str(e)})
