"""Sub-Agent G: Tactical Style Matching Analysis.

Analyses coaching formations, playing style, goal timing patterns,
and tactical compatibility between two teams to detect style clashes
that the market may not be pricing in.

Usage:
    python tactical_matchup.py <fixture_id> <league_id> <season>
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.api_football import (
    get_fixture_by_id,
    get_team_statistics,
    get_fixtures,
)
from utils import print_json


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


def analyse_style(fixtures: list[dict], team_id: int, team_name: str) -> dict:
    """Infer playing style from recent match statistics."""
    possession_vals = []
    passes_vals = []
    shots_vals = []
    shots_on_vals = []
    tackles_vals = []
    fouls_vals = []
    
    for f in fixtures[-5:]:  # Last 5 matches
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
                    try:
                        v = float(val.replace("%", "")) if isinstance(val, str) and "%" in val else float(val)
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
        peak_key = max(intervals, key=lambda k: 
            float(intervals[k].get("percentage", "0%").replace("%", "")) 
            if isinstance(intervals[k], dict) else 0)
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
    
    # Possession clash: high possession vs counter-attack
    home_tags = home_style.get("style_tags", [])
    away_tags = away_style.get("style_tags", [])
    
    if "possession-heavy" in home_tags and "counter-attack" in away_tags:
        clashes.append(f"{away_style['team_name']} counter-attack style targets {home_style['team_name']} high-line possession")
    if "possession-heavy" in away_tags and "counter-attack" in home_tags:
        clashes.append(f"{home_style['team_name']} counter-attack style targets {away_style['team_name']} high-line possession")
    
    # Press clash: high press vs passive defence
    if "high-press" in home_tags and "passive-defence" in away_tags:
        advantages.append(f"{home_style['team_name']} high press likely to disrupt {away_style['team_name']} build-up")
    if "high-press" in away_tags and "passive-defence" in home_tags:
        advantages.append(f"{away_style['team_name']} high press likely to disrupt {home_style['team_name']} build-up")
    
    # Shot volume mismatch
    home_shots = home_style.get("avg_shots", 0)
    away_shots = away_style.get("avg_shots", 0)
    if home_shots > away_shots * 1.5:
        advantages.append(f"{home_style['team_name']} significantly more shots ({home_shots}/game vs {away_shots})")
    elif away_shots > home_shots * 1.5:
        advantages.append(f"{away_style['team_name']} significantly more shots ({away_shots}/game vs {home_shots})")
    
    return {
        "key_clashes": clashes,
        "tactical_advantages": advantages,
        "clash_count": len(clashes),
        "advantage_count": len(advantages),
    }


def run(fixture_id: int, league_id: int, season: int) -> dict:
    fixture = get_fixture_by_id(fixture_id)
    if not fixture:
        return {"agent": "tactical_matchup", "fixture_id": fixture_id, "error": "Fixture not found"}
    
    f = fixture[0]
    home_id = f["teams"]["home"]["id"]
    away_id = f["teams"]["away"]["id"]
    home_name = f["teams"]["home"]["name"]
    away_name = f["teams"]["away"]["name"]
    
    # Team statistics (formations + goal timing)
    home_stats = get_team_statistics(home_id, league_id, season).get("response", {})
    away_stats = get_team_statistics(away_id, league_id, season).get("response", {})
    
    home_formation = extract_formation(home_stats)
    away_formation = extract_formation(away_stats)
    
    # Goal timing
    home_timing = analyse_goal_timing(home_stats)
    away_timing = analyse_goal_timing(away_stats)
    
    # Recent fixtures for style analysis
    home_fixtures = get_fixtures(league_id, season, team_id=home_id)
    away_fixtures = get_fixtures(league_id, season, team_id=away_id)
    
    # Sort by date descending, take completed ones
    home_recent = [fx for fx in home_fixtures if fx.get("fixture", {}).get("status", {}).get("short") == "FT"]
    away_recent = [fx for fx in away_fixtures if fx.get("fixture", {}).get("status", {}).get("short") == "FT"]
    home_recent.sort(key=lambda x: x.get("fixture", {}).get("date", ""), reverse=True)
    away_recent.sort(key=lambda x: x.get("fixture", {}).get("date", ""), reverse=True)
    
    # Get detailed stats for recent fixtures
    home_detail = []
    away_detail = []
    for fx in home_recent[:5]:
        fid = fx.get("fixture", {}).get("id")
        if fid:
            detail = get_fixture_by_id(fid)
            if detail:
                home_detail.append(detail[0])
    for fx in away_recent[:5]:
        fid = fx.get("fixture", {}).get("id")
        if fid:
            detail = get_fixture_by_id(fid)
            if detail:
                away_detail.append(detail[0])
    
    # Style analysis
    home_style = analyse_style(home_detail, home_id, home_name)
    away_style = analyse_style(away_detail, away_id, away_name)
    
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
        "notes": all_notes,
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print_json({"error": "Usage: tactical_matchup.py <fixture_id> <league_id> <season>"})
        sys.exit(1)
    fixture_id = int(sys.argv[1])
    league_id = int(sys.argv[2])
    season = int(sys.argv[3])
    try:
        result = run(fixture_id, league_id, season)
        print_json(result)
    except Exception as e:
        print_json({"agent": "tactical_matchup", "fixture_id": fixture_id, "error": str(e)})
