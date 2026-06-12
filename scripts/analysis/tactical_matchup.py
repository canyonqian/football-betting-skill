"""Sub-Agent G: Tactical Style Matching Analysis.

Analyses coaching formations, playing style, goal timing patterns,
and tactical compatibility between two teams to detect style clashes
that the market may not be pricing in.

Usage:
    python tactical_matchup.py <match_id> <competition_id> <season>
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.football_data import (
    get_team_statistics,
    get_teams,
    get_match,
    get_standings,
    get_head2head,
)
from utils import print_json

try:
    from soccerdata import FBref
    HAS_SOCCERDATA = True
except ImportError:
    HAS_SOCCERDATA = False


COMPETITION_TO_LEAGUE_ID = {
    "PL": 39, "BL1": 78, "SA": 135, "PD": 140, "FL1": 61, "CL": 2,
}

COMP_TO_FBREF = {
    "PL": "ENG-Premier League", "BL1": "GER-Bundesliga",
    "SA": "ITA-Serie A", "PD": "ESP-La Liga",
    "FL1": "FRA-Ligue 1", "CL": "UEFA-Champions League",
}


def get_fbref_stats(competition_id: str, season: int) -> dict:
    if not HAS_SOCCERDATA:
        return {"available": False}
    league = COMP_TO_FBREF.get(competition_id)
    if not league:
        return {"available": False}
    try:
        fbref = FBref(league, str(season))
        schedule = fbref.read_schedule()
        return {
            "available": True,
            "matches_count": len(schedule) if schedule is not None else 0,
        }
    except Exception:
        return {"available": False}


# Formation compatibility matrix: which formations counter which
# Key: attacker's formation, Value: defender formations it exploits
FORMATION_COUNTERS = {
    "3-5-2": ["4-3-3", "4-2-3-1", "4-4-2"],      # wingbacks exploit wide areas
    "3-4-3": ["4-3-3", "4-2-3-1"],                  # overload final third
    "4-3-3": ["4-4-2", "4-4-1-1"],                  # midfield 3v2 advantage
    "4-2-3-1": ["4-3-3", "4-4-2"],                  # #10 exploits gaps between lines
    "4-4-2": ["3-5-2", "3-4-3"],                    # two strikers vs 3-man backline
    "4-4-1-1": ["4-3-3"],                            # compact block frustrates possession
    "3-4-2-1": ["4-4-2", "4-3-3"],                  # overload central areas
    "5-3-2": ["4-3-3", "4-2-3-1"],                  # deep block + counter
    "5-4-1": ["4-3-3", "4-2-3-1"],                  # ultra-defensive
}


def normalize_formation(fmt: str) -> str:
    """Normalize formation string to standard format."""
    fmt = fmt.strip()
    # Handle variations like "4-3-3" or "4 3 3" or "4x3x3"
    for sep in [" ", "x"]:
        fmt = fmt.replace(sep, "-")
    return fmt


def extract_formation(team_stats: dict) -> str:
    """Extract the most-used formation from team statistics."""
    lineups = team_stats.get("lineups", [])
    if not lineups:
        return "Unknown"
    # Sort by played count, get the most-played
    best = max(lineups, key=lambda l: l.get("played", 0))
    return normalize_formation(best.get("formation", "Unknown"))


def analyse_style_from_season(team_stats: dict, team_name: str) -> dict:
    """Infer playing style from season-level statistics (NO per-fixture API calls).
    
    Uses lineups, goals/min, cards, clean sheets from /teams/statistics.
    Avoids per-fixture pulls — saves ~8 API calls per agent run.
    """
    # Goals per game (season average)
    goals = team_stats.get("goals", {})
    gpg_total = float(goals.get("for", {}).get("average", {}).get("total", 0) or 0)
    gpg_home = float(goals.get("for", {}).get("average", {}).get("home", 0) or 0)
    gpg_away = float(goals.get("for", {}).get("average", {}).get("away", 0) or 0)
    
    # Defensive
    total_played = int(team_stats.get("fixtures", {}).get("played", {}).get("total", 0) or 0)
    clean_sheets = int(team_stats.get("clean_sheet", {}).get("total", 0) or 0)
    cs_rate = clean_sheets / max(total_played, 1)
    failed_score = int(team_stats.get("failed_to_score", {}).get("total", 0) or 0)
    fts_rate = failed_score / max(total_played, 1)
    
    # Aggression
    cards = team_stats.get("cards", {})
    yellows = int(cards.get("yellow", {}).get("total", 0) or 0)
    reds = int(cards.get("red", {}).get("total", 0) or 0)
    cards_per_game = (yellows + reds * 5) / max(total_played, 1)
    
    # Form
    form = team_stats.get("form", "")
    
    # Style classification
    style = []
    if gpg_total >= 2.0:
        style.append("high-scoring")
    elif gpg_total <= 1.0:
        style.append("low-scoring")
    else:
        style.append("moderate-scoring")
    
    if cs_rate >= 0.4:
        style.append("solid-defence")
    elif cs_rate <= 0.15:
        style.append("leaky-defence")
    
    if cards_per_game >= 3.0:
        style.append("aggressive")
    elif cards_per_game <= 1.5:
        style.append("disciplined")
    
    if fts_rate <= 0.15:
        style.append("consistent-scorer")
    elif fts_rate >= 0.40:
        style.append("inconsistent-attack")
    
    return {
        "team_name": team_name,
        "goals_per_game": round(gpg_total, 2),
        "goals_per_game_home": round(gpg_home, 2),
        "goals_per_game_away": round(gpg_away, 2),
        "clean_sheet_rate": round(cs_rate, 2),
        "failed_to_score_rate": round(fts_rate, 2),
        "cards_per_game": round(cards_per_game, 2),
        "matches_played": total_played,
        "style_tags": style,
    }


def analyse_style(fixtures: list[dict], team_id: int, team_name: str) -> dict:
    """(Deprecated) Infer playing style from per-fixture stats. 
    Use analyse_style_from_season instead — saves API calls."""
    possession_vals = []
    passes_vals = []
    shots_vals = []
    shots_on_vals = []
    tackles_vals = []
    fouls_vals = []
    
    limit = min(3, len(fixtures))  # Reduced from 5 to 3
    for f in fixtures[-limit:]:
        stats = f.get("statistics", [])
        if not stats:
            continue
        # Find the stats for this team
        for team_stats in stats:
            if team_stats.get("team", {}).get("id") == team_id:
                s = team_stats.get("statistics", [])
                for stat_entry in s:
                    stype = stat_entry.get("type", "")
                    val = stat_entry.get("value")
                    if val is None:
                        continue
                    if not isinstance(val, (int, float, str)):
                        continue
                    try:
                        if isinstance(val, str) and "%" in val:
                            v = float(val.replace("%", ""))
                        else:
                            v = float(val)
                    except (ValueError, TypeError):
                        continue
                    
                    if stype == "Ball Possession":
                        possession_vals.append(v)
                    elif stype == "Total passes":
                        passes_vals.append(v)
                    elif stype == "Total shots":
                        shots_vals.append(v)
                    elif stype == "Shots on Goal":
                        shots_on_vals.append(v)
                    elif stype == "Total tackles":
                        tackles_vals.append(v)
                    elif stype == "Fouls":
                        fouls_vals.append(v)
                break
    
    def avg(vals):
        return round(sum(vals) / len(vals), 1) if vals else 0
    
    avg_possession = avg(possession_vals)
    avg_passes = avg(passes_vals)
    avg_shots = avg(shots_vals)
    avg_shots_on = avg(shots_on_vals)
    avg_tackles = avg(tackles_vals)
    avg_fouls = avg(fouls_vals)
    
    # Style classification
    style = []
    if avg_possession >= 55:
        style.append("possession-heavy")
    elif avg_possession <= 42:
        style.append("counter-attack")
    else:
        style.append("balanced-possession")
    
    if avg_shots >= 15:
        style.append("high-shot-volume")
    elif avg_shots <= 8:
        style.append("low-shot-volume")
    
    if avg_tackles >= 20:
        style.append("high-press")
    elif avg_tackles <= 12:
        style.append("passive-defence")
    
    if avg_fouls >= 14:
        style.append("aggressive")
    elif avg_fouls <= 8:
        style.append("disciplined")
    
    return {
        "team_name": team_name,
        "avg_possession": avg_possession,
        "avg_passes": avg_passes,
        "avg_shots": avg_shots,
        "avg_shots_on_target": avg_shots_on,
        "avg_tackles": avg_tackles,
        "avg_fouls": avg_fouls,
        "matches_analysed": len(possession_vals),
        "style_tags": style,
    }


def analyse_goal_timing(team_stats: dict) -> dict:
    """Analyze when a team scores and concedes goals."""
    goals_for = team_stats.get("goals", {}).get("for", {}).get("minute", {})
    goals_against = team_stats.get("goals", {}).get("against", {}).get("minute", {})
    
    def parse_minute_intervals(data: dict) -> dict:
        result = {}
        for key, val in data.items():
            interval = key.replace("-", "′–").replace("'", "′")
            try:
                result[interval] = {
                    "total": val.get("total", 0),
                    "percentage": val.get("percentage", "0%"),
                }
            except (AttributeError, TypeError):
                result[interval] = val
        return result
    
    for_intervals = parse_minute_intervals(goals_for) if isinstance(goals_for, dict) else {}
    against_intervals = parse_minute_intervals(goals_against) if isinstance(goals_against, dict) else {}
    
    # Find peak scoring/conceding periods
    def find_peak(intervals: dict) -> str:
        if not intervals:
            return "unknown"
        def extract_pct(k: str) -> float:
            if not isinstance(intervals[k], dict):
                return 0
            pct = intervals[k].get("percentage")
            if pct is None or not isinstance(pct, str):
                return 0
            try:
                return float(pct.replace("%", ""))
            except (ValueError, TypeError):
                return 0
        peak_key = max(intervals, key=extract_pct)
        return peak_key
    
    peak_scoring = find_peak(for_intervals)
    peak_conceding = find_peak(against_intervals)
    
    # Classify: early, mid, late dominant
    def classify_timing(peak: str) -> str:
        if not peak or peak == "unknown":
            return "balanced"
        try:
            # Extract start minute (e.g., "61-75")
            start = int(peak.split("′")[0].split("-")[0])
            if start <= 30:
                return "early-dominant"
            elif start >= 61:
                return "late-dominant"
            else:
                return "mid-dominant"
        except (ValueError, IndexError):
            return "balanced"
    
    return {
        "peak_scoring_period": peak_scoring,
        "peak_conceding_period": peak_conceding,
        "scoring_pattern": classify_timing(peak_scoring),
        "conceding_pattern": classify_timing(peak_conceding),
        "goals_for_by_minute": for_intervals,
        "goals_against_by_minute": against_intervals,
    }


def compute_style_clash(home_style: dict, away_style: dict, 
                        home_form: str, away_form: str) -> dict:
    """Compute tactical compatibility score."""
    clashes = []
    advantages = []
    
    home_tags = home_style.get("style_tags", [])
    away_tags = away_style.get("style_tags", [])
    
    # Scoring power mismatch
    home_gpg = home_style.get("goals_per_game", 0)
    away_gpg = away_style.get("goals_per_game", 0)
    if home_gpg > away_gpg * 1.5:
        advantages.append(f"{home_style['team_name']} much higher scoring ({home_gpg}/game vs {away_gpg})")
    elif away_gpg > home_gpg * 1.5:
        advantages.append(f"{away_style['team_name']} much higher scoring ({away_gpg}/game vs {home_gpg})")
    
    # Defence quality mismatch
    home_cs = home_style.get("clean_sheet_rate", 0)
    away_cs = away_style.get("clean_sheet_rate", 0)
    if "solid-defence" in home_tags and "leaky-defence" in away_tags:
        advantages.append(f"{home_style['team_name']} solid defence vs {away_style['team_name']} leaky defence")
    if "solid-defence" in away_tags and "leaky-defence" in home_tags:
        advantages.append(f"{away_style['team_name']} solid defence vs {home_style['team_name']} leaky defence")
    
    # Attack consistency
    if "consistent-scorer" in home_tags and "leaky-defence" in away_tags:
        advantages.append(f"{home_style['team_name']} consistent attack vs {away_style['team_name']} leaky defence")
    if "consistent-scorer" in away_tags and "leaky-defence" in home_tags:
        advantages.append(f"{away_style['team_name']} consistent attack vs {home_style['team_name']} leaky defence")
    
    # Aggression clash — aggressive vs disciplined
    if "aggressive" in home_tags and "disciplined" in away_tags:
        clashes.append(f"{home_style['team_name']} aggressive style may draw fouls from {away_style['team_name']} disciplined setup")
    if "aggressive" in away_tags and "disciplined" in home_tags:
        clashes.append(f"{away_style['team_name']} aggressive style may draw fouls from {home_style['team_name']} disciplined setup")
    
    return {
        "key_clashes": clashes,
        "tactical_advantages": advantages,
        "clash_count": len(clashes),
        "advantage_count": len(advantages),
    }


def run(match_id: int, competition_id: str, season: int) -> dict:
    match = get_match(match_id)
    if not match:
        return {"agent": "tactical_matchup", "match_id": match_id, "error": "Match not found"}

    home_name = match.get("homeTeam", {}).get("name", "")
    away_name = match.get("awayTeam", {}).get("name", "")

    standings = get_standings(competition_id, season)
    h2h = get_head2head(match_id)

    league_id = COMPETITION_TO_LEAGUE_ID.get(competition_id)
    if league_id:
        home_search = get_teams(name=home_name, league_id=league_id, season=season) or []
        away_search = get_teams(name=away_name, league_id=league_id, season=season) or []
        home_id = home_search[0]["team"]["id"] if home_search else None
        away_id = away_search[0]["team"]["id"] if away_search else None
    else:
        home_id = away_id = None

    if not home_id or not away_id:
        return {"agent": "tactical_matchup", "match_id": match_id, "error": "Could not resolve team IDs in football-data.org"}

    # Team statistics (formations + goal timing)
    home_stats = get_team_statistics(home_id, league_id, season).get("response", {})
    away_stats = get_team_statistics(away_id, league_id, season).get("response", {})

    home_formation = extract_formation(home_stats)
    away_formation = extract_formation(away_stats)

    # Goal timing
    home_timing = analyse_goal_timing(home_stats)
    away_timing = analyse_goal_timing(away_stats)

    # Style analysis from season stats (avoids per-fixture API calls)
    home_style = analyse_style_from_season(home_stats, home_name)
    away_style = analyse_style_from_season(away_stats, away_name)

    # Soccerdata enrichment
    fbref_stats = get_fbref_stats(competition_id, season)

    # Formation compatibility
    home_form = home_stats.get("form", "")
    away_form = away_stats.get("form", "")
    clashes = compute_style_clash(home_style, away_style, home_form, away_form)

    # Formation counter check
    formation_notes = []
    if home_formation in FORMATION_COUNTERS and away_formation in FORMATION_COUNTERS.get(home_formation, []):
        formation_notes.append(f"{home_formation} vs {away_formation}: {home_name} formation has tactical edge")
    if away_formation in FORMATION_COUNTERS and home_formation in FORMATION_COUNTERS.get(away_formation, []):
        formation_notes.append(f"{away_formation} vs {home_formation}: {away_name} formation has tactical edge")
    if not formation_notes:
        formation_notes.append(f"{home_formation} vs {away_formation}: No clear formation advantage")

    # Timing clash
    timing_notes = []
    if home_timing.get("scoring_pattern") == "early-dominant" and away_timing.get("conceding_pattern") == "early-dominant":
        timing_notes.append(f"{home_name} scores early, {away_name} concedes early — potential fast start for {home_name}")
    if away_timing.get("scoring_pattern") == "early-dominant" and home_timing.get("conceding_pattern") == "early-dominant":
        timing_notes.append(f"{away_name} scores early, {home_name} concedes early — potential fast start for {away_name}")
    if home_timing.get("scoring_pattern") == "late-dominant" and away_timing.get("conceding_pattern") == "late-dominant":
        timing_notes.append(f"{home_name} scores late, {away_name} concedes late — watch final 15 minutes")

    # Build finding
    all_notes = formation_notes + timing_notes + clashes.get("key_clashes", []) + clashes.get("tactical_advantages", [])

    finding_parts = []
    if formation_notes:
        finding_parts.append(formation_notes[0])
    if timing_notes:
        finding_parts.append(timing_notes[0])
    if clashes.get("key_clashes"):
        finding_parts.append(clashes["key_clashes"][0])

    finding = " | ".join(finding_parts[:3]) if finding_parts else "Tactical styles analysed"

    # Signal strength
    if clashes.get("clash_count", 0) >= 2 or len(timing_notes) >= 2:
        strength = "strong"
    elif clashes.get("clash_count", 0) >= 1 or len(timing_notes) >= 1 or len(formation_notes) > 1:
        strength = "medium"
    else:
        strength = "weak"

    return {
        "agent": "tactical_matchup",
        "fixture": f"{home_name} vs {away_name}",
        "finding": finding,
        "signal_strength": strength,
        "key_metrics": {
            "home": {
                "formation": home_formation,
                "goal_timing": home_timing,
                "style": {k: v for k, v in home_style.items() if k not in ("team_name",)},
            },
            "away": {
                "formation": away_formation,
                "goal_timing": away_timing,
                "style": {k: v for k, v in away_style.items() if k not in ("team_name",)},
            },
            "style_clash": clashes,
        },
        "fbref_stats": fbref_stats,
        "standings_summary": {
            "total_groups": len(standings),
            "has_data": len(standings) > 0,
        },
        "h2h_summary": {
            "previous_meetings": h2h.get("resultSet", {}).get("count", 0) if isinstance(h2h, dict) else 0,
        },
        "search_queries": [
            f"{home_name} vs {away_name} predicted lineup {season}",
            f"{home_name} confirmed formation {season}",
            f"{away_name} confirmed formation {season}",
        ],
        "notes": all_notes,
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
