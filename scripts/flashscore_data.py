"""Flashscore Data â€?lineups, formations, injuries via Playwright.

Usage:
    python flashscore_data.py "Brazil" "Morocco"

Output: JSON with formations, starting XI, player positions, injuries.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from api.scraper import FlashscoreScraper
from utils import print_json


def run(home_team: str, away_team: str) -> dict:
    try:
        scraper = FlashscoreScraper(headless=True, timeout=30000)
        matches = scraper.search_match(home_team, away_team)
        if not matches:
            return {"error": "No Flashscore match found"}

        match_url = None
        for m in matches:
            txt = m.get("text", "")
            if home_team.lower() in txt.lower() and away_team.lower() in txt.lower():
                match_url = m["url"]
                break
        if not match_url:
            match_url = matches[0]["url"]

        ld = scraper.get_match_data(match_url)

        players_detail = {}
        for team, xi in ld.get("starting_xi", {}).items():
            players_detail[team] = []
            for p in xi:
                players_detail[team].append({
                    "name": p.get("name", ""),
                    "number": p.get("number", ""),
                    "position": p.get("position", ""),
                    "age": p.get("age", ""),
                })

        return {
            "available": bool(ld.get("formations") or ld.get("starting_xi")),
            "formations": ld.get("formations", {}),
            "starting_xi": players_detail,
            "injuries": ld.get("injuries", []),
            "notes": [],
        }
    except Exception as e:
        return {"error": str(e), "available": False}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print_json({"error": "Usage: flashscore_data.py <home_team> <away_team>"})
        sys.exit(1)
    try:
        result = run(sys.argv[1], sys.argv[2])
        print_json(result)
    except Exception as e:
        print_json({"error": str(e)})
