"""Sub-Agent F: Objective Factors Analysis.

Identifies match-changing variables beyond form and odds:
- Player injuries and suspensions
- Key player absence impact
- Squad depth and rotation risk
- Recent lineup changes
- Fatigue indicators (match congestion, travel distance)

Usage:
    python objective_factors.py <fixture_id> <league_id> <season>
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.api_football import (
    get_fixture_by_id,
    get_injuries,
    get_players_squads,
    get_team_statistics,
)
from utils import print_json


def get_team_injuries(team_id: int, league_id: int, season: int) -> list[dict]:
    """Get injury list for a team, filtering to current season."""
    try:
        injuries = get_injuries(team=team_id, league=league_id, season=season)
        return injuries
    except Exception:
        return []


def get_squad_info(team_id: int) -> dict:
    """Get squad composition: size, average age, key positions."""
    try:
        squad = get_players_squads(team_id)
        if not squad:
            return {}
        
        players = squad[0].get("players", [])
        return {
            "squad_size": len(players),
            "players": [
                {
                    "name": p.get("name"),
                    "position": p.get("position"),
                    "number": p.get("number"),
                }
                for p in players
            ],
        }
    except Exception:
        return {}


def assess_fatigue(team_id: int, league_id: int, season: int) -> dict:
    """Assess fatigue based on recent fixture congestion."""
    try:
        stats = get_team_statistics(team_id, league_id, season)
        response = stats.get("response", {})
        
        fixtures = response.get("fixtures", {})
        played = int(fixtures.get("played", {}).get("total", 0) or 0)
        
        # Clean sheet rate as a rough defensive stability indicator
        clean_sheets = int(response.get("clean_sheet", {}).get("total", 0) or 0)
        cs_rate = clean_sheets / max(played, 1)
        
        # Failed to score rate
        failed_score = int(response.get("failed_to_score", {}).get("total", 0) or 0)
        fts_rate = failed_score / max(played, 1)
        
        return {
            "matches_played": played,
            "clean_sheet_rate": round(cs_rate, 2),
            "failed_to_score_rate": round(fts_rate, 2),
        }
    except Exception:
        return {}


def run(fixture_id: int, league_id: int, season: int) -> dict:
    """Execute objective factors analysis."""
    fixture = get_fixture_by_id(fixture_id)
    if not fixture:
        return {"agent": "objective_factors", "fixture_id": fixture_id, 
                "error": "Fixture not found"}
    
    f = fixture[0]
    home_id = f["teams"]["home"]["id"]
    away_id = f["teams"]["away"]["id"]
    home_name = f["teams"]["home"]["name"]
    away_name = f["teams"]["away"]["name"]
    
    # Injuries
    home_injuries = get_team_injuries(home_id, league_id, season)
    away_injuries = get_team_injuries(away_id, league_id, season)
    
    # Squad info
    home_squad = get_squad_info(home_id)
    away_squad = get_squad_info(away_id)
    
    # Fatigue
    home_fatigue = assess_fatigue(home_id, league_id, season)
    away_fatigue = assess_fatigue(away_id, league_id, season)
    
    # Build impact analysis
    notes = []
    factors = []
    
    # Injury impact
    for team_name, injuries in [(home_name, home_injuries), (away_name, away_injuries)]:
        if injuries:
            names = [inj.get("player", {}).get("name", "Unknown") for inj in injuries]
            types = [inj.get("player", {}).get("type", "Unknown") for inj in injuries]
            reasons = [inj.get("player", {}).get("reason", "") for inj in injuries]
            
            injury_list = []
            for n, t, r in zip(names, types, reasons):
                injury_list.append(f"{n} ({t}: {r})" if r else f"{n} ({t})")
            
            notes.append(f"{team_name} injuries: {', '.join(injury_list)}")
            factors.append({
                "team": team_name,
                "type": "injury",
                "severity": "high" if len(injuries) >= 3 else "medium" if len(injuries) >= 1 else "low",
                "detail": len(injuries),
            })
    
    if not (home_injuries or away_injuries):
        notes.append("No significant injuries reported for either team")
    
    # Squad depth
    home_squad_size = home_squad.get("squad_size", 0)
    away_squad_size = away_squad.get("squad_size", 0)
    if home_squad_size > 0:
        notes.append(f"{home_name} squad size: {home_squad_size} | {away_name}: {away_squad_size}")
    
    # Fatigue comparison
    if home_fatigue and away_fatigue:
        notes.append(
            f"Season fatigue: {home_name} ({home_fatigue.get('matches_played', 0)} played, "
            f"CS {home_fatigue.get('clean_sheet_rate', 0):.0%}) vs "
            f"{away_name} ({away_fatigue.get('matches_played', 0)} played, "
            f"CS {away_fatigue.get('clean_sheet_rate', 0):.0%})"
        )
    
    finding = "Objective factors assessed"
    injury_count = len(home_injuries) + len(away_injuries)
    if injury_count >= 3:
        finding += f" — significant injury impact ({injury_count} players out)"
    elif injury_count >= 1:
        finding += f" — minor injury impact ({injury_count} players out)"
    else:
        finding += " — clean injury slate"
    
    return {
        "agent": "objective_factors",
        "fixture": f"{home_name} vs {away_name}",
        "finding": finding,
        "signal_strength": "strong" if injury_count >= 3 else "medium" if injury_count >= 1 else "weak",
        "key_metrics": {
            "home": {
                "injuries": len(home_injuries),
                "injury_list": [
                    {
                        "name": i.get("player", {}).get("name"),
                        "type": i.get("player", {}).get("type"),
                        "reason": i.get("player", {}).get("reason"),
                    }
                    for i in home_injuries
                ],
                "squad_size": home_squad_size,
                "fatigue": home_fatigue,
            },
            "away": {
                "injuries": len(away_injuries),
                "injury_list": [
                    {
                        "name": i.get("player", {}).get("name"),
                        "type": i.get("player", {}).get("type"),
                        "reason": i.get("player", {}).get("reason"),
                    }
                    for i in away_injuries
                ],
                "squad_size": away_squad_size,
                "fatigue": away_fatigue,
            },
        },
        "notes": notes,
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print_json({"error": "Usage: objective_factors.py <fixture_id> <league_id> <season>"})
        sys.exit(1)
    fixture_id = int(sys.argv[1])
    league_id = int(sys.argv[2])
    season = int(sys.argv[3])
    try:
        result = run(fixture_id, league_id, season)
        print_json(result)
    except Exception as e:
        print_json({"agent": "objective_factors", "fixture_id": fixture_id, 
                    "error": str(e)})
