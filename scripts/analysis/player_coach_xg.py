"""Sub-Agent H: Player & Coach + xG Analysis.

Analyses player impact, coach experience, xG discrepancy, and squad quality
to identify match-changing variables that the market may be mispricing.

Usage:
    python player_coach_xg.py <fixture_id> <league_id> <season>
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.api_football import (
    get_fixture_by_id,
    get_team_statistics,
    get_injuries,
    get_predictions,
    get_players,
)
from utils import print_json


# League name mapping for soccerdata (Understat format)
LEAGUE_TO_UNDERSTAT = {
    39: "ENG-Premier League",
    140: "ESP-La Liga", 
    78: "GER-Bundesliga",
    135: "ITA-Serie A",
    61: "FRA-Ligue 1",
    2: None,   # Champions League not in Understat
    1: None,   # World Cup not in Understat
    4: None,   # Euros not in Understat
}


def get_xg_data(league_id: int, season: int) -> dict:
    """Attempt to get xG data from soccerdata (Understat).
    Falls back to shots-based xG proxy if unavailable.
    Returns empty dict if no data available.
    """
    try:
        from soccerdata import Understat
        league_name = LEAGUE_TO_UNDERSTAT.get(league_id)
        if not league_name:
            return {"source": "unavailable", "note": f"League {league_id} not in Understat coverage"}
        
        # soccerdata season format: "2025"
        u = Understat(leagues=league_name, seasons=str(season))
        schedule = u.read_schedule()
        if schedule is not None and not schedule.empty:
            return {
                "source": "understat",
                "data_available": True,
                "matches_count": len(schedule),
            }
        return {"source": "understat", "data_available": False, "note": "No data returned"}
    except ImportError:
        return {"source": "fallback", "note": "soccerdata not installed. Install: pip install soccerdata"}
    except Exception as e:
        return {"source": "fallback", "note": f"Understat error: {str(e)[:100]}"}


def compute_xg_proxy(team_stats: dict, team_name: str) -> dict:
    """Compute xG proxy metrics from shots data when real xG is unavailable."""
    goals = team_stats.get("goals", {})
    goals_for = goals.get("for", {}).get("total", {})
    total_goals = int(goals_for.get("total", 0) or 0)
    matches_played = int(team_stats.get("fixtures", {}).get("played", {}).get("total", 0) or 0)
    
    # We can't get shot counts from team_stats (not available)
    # Use goals per match as baseline
    gpg = total_goals / max(matches_played, 1)
    
    # Use predictions data if available for goal projections
    return {
        "goals_per_game": round(gpg, 2),
        "total_goals": total_goals,
        "matches_played": matches_played,
        "note": "Real xG not available. Using goals per game as baseline. Install soccerdata for Understat xG.",
    }


def analyse_coach(team_id: int, team_name: str) -> dict:
    """Analyze coach data from API."""
    try:
        from api.api_football import _get
        coach_data = _get("coachs", {"team": team_id}).get("response", [])
    except Exception:
        return {"team_name": team_name, "available": False, "note": "Coach endpoint not available"}

    if not coach_data:
        return {"team_name": team_name, "available": False, "note": "No coach data"}

    coach = coach_data[0]
    career = coach.get("career", [])
    
    # Count teams managed
    teams_managed = len(set(c.get("team", {}).get("id") for c in career if c.get("team", {}).get("id")))
    
    # Calculate total career span
    start_dates = [c.get("start") for c in career if c.get("start")]
    end_dates = [c.get("end") for c in career if c.get("end")]
    
    experience_level = "veteran" if teams_managed >= 5 else "experienced" if teams_managed >= 3 else "developing"
    
    return {
        "team_name": team_name,
        "available": True,
        "coach_name": coach.get("name", "Unknown"),
        "age": coach.get("age"),
        "nationality": coach.get("nationality"),
        "teams_managed": teams_managed,
        "career_entries": len(career),
        "experience_level": experience_level,
    }


def analyse_squad_impact(team_id: int, league_id: int, season: int, team_name: str) -> dict:
    """Analyze squad quality and injury impact."""
    # Get injuries
    try:
        injuries = get_injuries(team=team_id, league=league_id, season=season)
    except Exception:
        injuries = []
    
    # Get player stats for the team
    try:
        players = get_players(team=team_id, league=league_id, season=season, page=1)
    except Exception:
        players = []
    
    # Count positions
    positions = {}
    for p in players:
        for stat in p.get("statistics", []):
            pos = stat.get("games", {}).get("position", "Unknown")
            positions[pos] = positions.get(pos, 0) + 1
    
    injury_count = len(injuries)
    injury_names = []
    for inj in injuries:
        player = inj.get("player", {})
        name = player.get("name", "Unknown")
        reason = player.get("reason", "Unknown")
        injury_names.append(f"{name} ({reason})")
    
    return {
        "team_name": team_name,
        "players_with_stats": len(players),
        "positions": positions,
        "injury_count": injury_count,
        "injuries": injury_names,
        "injury_impact": "high" if injury_count >= 3 else "medium" if injury_count >= 1 else "low",
    }


def run(fixture_id: int, league_id: int, season: int) -> dict:
    fixture = get_fixture_by_id(fixture_id)
    if not fixture:
        return {"agent": "player_coach_xg", "fixture_id": fixture_id, "error": "Fixture not found"}
    
    f = fixture[0]
    home_id = f["teams"]["home"]["id"]
    away_id = f["teams"]["away"]["id"]
    home_name = f["teams"]["home"]["name"]
    away_name = f["teams"]["away"]["name"]
    
    # 1. Coach analysis
    home_coach = analyse_coach(home_id, home_name)
    away_coach = analyse_coach(away_id, away_name)
    
    # 2. Squad & injury impact
    home_squad = analyse_squad_impact(home_id, league_id, season, home_name)
    away_squad = analyse_squad_impact(away_id, league_id, season, away_name)
    
    # 3. xG data
    xg_source = get_xg_data(league_id, season)
    
    # 4. xG proxy from team stats
    home_stats = get_team_statistics(home_id, league_id, season).get("response", {})
    away_stats = get_team_statistics(away_id, league_id, season).get("response", {})
    home_xg_proxy = compute_xg_proxy(home_stats, home_name)
    away_xg_proxy = compute_xg_proxy(away_stats, away_name)
    
    # 5. Predictions as additional proxy
    try:
        preds = get_predictions(fixture_id)
        predictions_data = preds[0].get("predictions", {}) if preds else {}
    except Exception:
        predictions_data = {}
    
    # Build findings
    notes = []
    finding_parts = []
    
    # Coach comparison
    if home_coach.get("available") and away_coach.get("available"):
        home_exp = home_coach.get("experience_level", "unknown")
        away_exp = away_coach.get("experience_level", "unknown")
        h_teams = home_coach.get("teams_managed", 0)
        a_teams = away_coach.get("teams_managed", 0)
        
        if h_teams > a_teams + 2:
            notes.append(f"{home_name} coach ({home_coach['coach_name']}) has more experience ({h_teams} vs {a_teams} teams)")
        elif a_teams > h_teams + 2:
            notes.append(f"{away_name} coach ({away_coach['coach_name']}) has more experience ({a_teams} vs {h_teams} teams)")
        
        finding_parts.append(f"{home_name}: {h_teams} teams coached | {away_name}: {a_teams} teams")
    
    # Injury impact
    if home_squad.get("injury_count", 0) > 0:
        notes.append(f"{home_name} missing {home_squad['injury_count']} players: {', '.join(home_squad['injuries'][:3])}")
    if away_squad.get("injury_count", 0) > 0:
        notes.append(f"{away_name} missing {away_squad['injury_count']} players: {', '.join(away_squad['injuries'][:3])}")
    
    # xG notes
    if xg_source.get("source") == "understat" and xg_source.get("data_available"):
        notes.append("xG data available from Understat")
    else:
        notes.append(f"xG: {xg_source.get('note', 'unavailable')}. Using goals/game proxy.")
    
    if predictions_data:
        advice = predictions_data.get("advice")
        if advice:
            notes.append(f"Model prediction: {advice}")
        winner = predictions_data.get("winner", {})
        if winner:
            notes.append(f"Predicted winner: {winner.get('name', 'unknown')} ({winner.get('comment', '')})")
    
    # Build finding
    finding = " | ".join(finding_parts) if finding_parts else "Player, coach and xG data analysed"
    
    # Strength
    injury_total = home_squad.get("injury_count", 0) + away_squad.get("injury_count", 0)
    if (home_coach.get("available") and away_coach.get("available")) and injury_total >= 2:
        strength = "strong"
    elif home_coach.get("available") or injury_total >= 1:
        strength = "medium"
    else:
        strength = "weak"
    
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
            "xg_proxy": {
                "home": home_xg_proxy,
                "away": away_xg_proxy,
            },
            "predictions": {
                "advice": predictions_data.get("advice"),
                "percent": predictions_data.get("percent", {}),
            },
        },
        "notes": notes,
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print_json({"error": "Usage: player_coach_xg.py <fixture_id> <league_id> <season>"})
        sys.exit(1)
    fixture_id = int(sys.argv[1])
    league_id = int(sys.argv[2])
    season = int(sys.argv[3])
    try:
        result = run(fixture_id, league_id, season)
        print_json(result)
    except Exception as e:
        print_json({"agent": "player_coach_xg", "fixture_id": fixture_id, "error": str(e)})
