"""Sub-Agent H: Player & Coach + xG Analysis.

Analyses player impact, lineup quality, and xG discrepancy using:
- Flashscore scraper for starting XI and player positions
- soccerdata/Understat for xG data (if installed)
- Web search for coach info

Usage:
    python player_coach_xg.py <match_id> <competition_id> <season>
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.football_data import get_match
from api.scraper import FlashscoreScraper
from utils import print_json

try:
    from soccerdata import Understat
    HAS_XG = True
except ImportError:
    HAS_XG = False

COMP_TO_UNDERSTAT = {
    "PL": "ENG-Premier League", "BL1": "GER-Bundesliga",
    "SA": "ITA-Serie A", "PD": "ESP-La Liga",
    "FL1": "FRA-Ligue 1",
}


def get_xg_data(competition_id: str, season: int) -> dict:
    """Get real xG from Understat via soccerdata."""
    if not HAS_XG:
        return {"source": "not_installed", "note": "pip install soccerdata"}
    league = COMP_TO_UNDERSTAT.get(competition_id)
    if not league:
        return {"source": "unavailable", "note": f"{competition_id} not in Understat"}
    try:
        u = Understat(leagues=league, seasons=str(season))
        schedule = u.read_schedule()
        if schedule is not None and not schedule.empty:
            return {"source": "understat", "available": True, "matches": len(schedule)}
        return {"source": "understat", "available": False}
    except Exception as e:
        return {"source": "error", "note": str(e)[:100]}


def fetch_lineup_analysis(home_name: str, away_name: str) -> dict:
    """Fetch lineups from Flashscore and extract player data."""
    result = {"formations": {}, "players": {}, "positions": {}, "available": False}
    try:
        scraper = FlashscoreScraper(headless=True, timeout=30000)
        matches = scraper.search_match(home_name, away_name)
        if not matches:
            return result

        match_url = None
        for m in matches:
            txt = m.get("text", "")
            if home_name.lower() in txt.lower() and away_name.lower() in txt.lower():
                match_url = m["url"]
                break
        if not match_url:
            match_url = matches[0]["url"]

        ld = scraper.get_match_data(match_url)
        result["formations"] = ld.get("formations", {})
        result["players"] = ld.get("starting_xi", {})
        result["available"] = bool(result.get("players"))

        # Count positions per team
        for team, xi in result["players"].items():
            pos_counts = {}
            for p in xi:
                pos = p.get("position", "")
                if pos:
                    pos_counts[pos] = pos_counts.get(pos, 0) + 1
            result["positions"][team] = pos_counts

    except Exception:
        pass
    return result


def run(match_id: int, competition_id: str, season: int) -> dict:
    match_data = get_match(match_id)
    if not match_data:
        return {"agent": "player_coach_xg", "match_id": match_id, "error": "Match not found"}

    home_team = match_data.get("homeTeam", {})
    away_team = match_data.get("awayTeam", {})
    home_name = home_team.get("name", "Unknown")
    away_name = away_team.get("name", "Unknown")

    # Lineup data from Flashscore
    lineup = fetch_lineup_analysis(home_name, away_name)

    # xG data from soccerdata
    xg_source = get_xg_data(competition_id, season)

    # Build notes
    notes = []
    search_queries = [
        f"{home_name} coach tactical approach style",
        f"{away_name} coach tactical approach style",
        f"{home_name} {away_name} team news injuries {season}",
    ]

    if lineup.get("available"):
        for team, formation in lineup.get("formations", {}).items():
            notes.append(f"{team} formation: {formation}")
        for team, xi in lineup.get("players", {}).items():
            if xi:
                names = [p["name"] for p in xi]
                notes.append(f"{team} starting XI ({len(xi)}): {', '.join(names)}")
        for team, pos_counts in lineup.get("positions", {}).items():
            parts = [f"{v} {k}" for k, v in sorted(pos_counts.items())]
            notes.append(f"{team} lineup: {', '.join(parts)}")
        notes.append("Coach info not available from data sources. Use web search.")
    else:
        notes.append("Lineup data unavailable from Flashscore. Use web search for team news.")
        search_queries.insert(0, f"{home_name} vs {away_name} predicted lineup formation")

    if xg_source.get("source") == "understat" and xg_source.get("available"):
        notes.append(f"xG data available from Understat ({xg_source.get('matches', '?')} matches)")
    else:
        notes.append(f"xG: {xg_source.get('source', 'unavailable')}. Skipping xG analysis.")

    # Signal strength
    has_lineups = lineup.get("available", False)
    has_xg = xg_source.get("source") == "understat" and xg_source.get("available")

    if has_lineups and has_xg:
        strength = "strong"
    elif has_lineups:
        strength = "medium"
    elif has_xg:
        strength = "medium"
    else:
        strength = "weak"

    finding = f"Player and lineup analysis for {home_name} vs {away_name}"
    if has_lineups:
        home_xi = len(lineup.get("players", {}).get(home_name, []))
        away_xi = len(lineup.get("players", {}).get(away_name, []))
        finding += f" ({home_xi}v{away_xi} players in starting XI)"

    return {
        "agent": "player_coach_xg",
        "fixture": f"{home_name} vs {away_name}",
        "finding": finding,
        "signal_strength": strength,
        "key_metrics": {
            "lineups": lineup,
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
