"""Sub-Agent G: Tactical Style Matching Analysis.

Analyses formations, playing style, and tactical compatibility.
Uses football-data.org + soccerdata + web search guidance.

Usage:
    python tactical_matchup.py <match_id> <competition_id> <season>
"""

import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.football_data import get_match, get_standings, get_head2head
from api.scraper import FlashscoreScraper
from utils import print_json

HAS_SOCCERDATA = False  # soccerdata import can cause network issues; disabled for now

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
    return {"available": False, "note": "soccerdata disabled"}
    # Note: full soccerdata integration requires FBref initialization
    # which can trigger network requests and exceed rate limits


def get_league_position(standings: list, team_id: int) -> int:
    """Find a team's league position from standings data."""
    for entry in standings:
        for row in entry.get("table", []):
            if row.get("team", {}).get("id") == team_id:
                return row.get("position", 0)
    return 0


def classify_style(team_name: str, league_pos: int) -> dict:
    """Classify team style from available data."""
    tags = []
    if league_pos <= 4:
        tags.append("top-tier")
    elif league_pos >= 15:
        tags.append("struggling")
    else:
        tags.append("mid-table")
    return {
        "team": team_name,
        "league_position": league_pos,
        "style_tags": tags,
    }


def compute_clash(home_info: dict, away_info: dict, formation_notes: list) -> dict:
    """Compute tactical compatibility."""
    clashes = []
    advantages = []

    home_pos = home_info.get("league_position", 10)
    away_pos = away_info.get("league_position", 10)
    home_name = home_info.get("team", "Home")
    away_name = away_info.get("team", "Away")

    if home_pos <= 4 and away_pos >= 15:
        advantages.append(f"{home_name} top-4 side vs struggling {away_name}")
    if away_pos <= 4 and home_pos >= 15:
        advantages.append(f"{away_name} top-4 side vs struggling {home_name}")

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

    # Team info — get_team() restricted on free tier, use standings + match data instead
    home_team = {"name": home_name, "id": home_id}
    away_team = {"name": away_name, "id": away_id}

    # Standings
    standings = get_standings(competition_id)
    home_pos = get_league_position(standings, home_id)
    away_pos = get_league_position(standings, away_id)

    # Style classification
    home_style = classify_style(home_name, home_pos)
    away_style = classify_style(away_name, away_pos)

    # Form from standings/position (no team endpoint data)
    home_form = ""
    away_form = ""

    # H2H context
    try:
        h2h = get_head2head(match_id)
        h2h_count = len(h2h.get("matches", [])) if isinstance(h2h, dict) else len(h2h) if isinstance(h2h, list) else 0
    except Exception:
        h2h_count = 0

    # Formation analysis via Flashscore scraper
    formation_notes = []
    lineups_data = {}
    try:
        scraper = FlashscoreScraper(headless=True, timeout=30000)
        matches = scraper.search_match(home_name, away_name)
        if matches:
            # Find best match (prefer exact team name match)
            match_url = None
            for m in matches:
                txt = m.get("text", "")
                if home_name.lower() in txt.lower() and away_name.lower() in txt.lower():
                    match_url = m["url"]
                    break
            if not match_url and matches:
                match_url = matches[0]["url"]

            if match_url:
                ld = scraper.get_match_data(match_url)
                lineups_data = ld

                for team, formation in ld.get("formations", {}).items():
                    formation_notes.append(f"{team} probable formation: {formation}")

                for team, xi in ld.get("starting_xi", {}).items():
                    if xi:
                        names = [p["name"] for p in xi[:5]]
                        formation_notes.append(f"{team} likely XI: {', '.join(names)}{'...' if len(xi) > 5 else ''}")

                injuries = ld.get("injuries", [])
                for inj in injuries:
                    formation_notes.append(f"Injury — {inj['team']}: {inj['player']} ({inj['reason']})")

                if formation_notes:
                    formation_notes.append("Source: Flashscore predicted lineups")
    except Exception:
        formation_notes.append(f"Formation data unavailable from Flashscore. Web search for {home_name} vs {away_name} lineups.")

    # Soccerdata stats
    fbref_data = get_style_from_fbref(competition_id, season)

    # Clash analysis
    clash = compute_clash(home_style, away_style, formation_notes)

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
            "formations": lineups_data.get("formations", {}),
            "lineups": {
                "home_starting_xi": lineups_data.get("starting_xi", {}).get(home_name, []),
                "away_starting_xi": lineups_data.get("starting_xi", {}).get(away_name, []),
            } if lineups_data else {},
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
