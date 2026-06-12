"""Flashscore scraper using Playwright for lineups, formations, and player data.

Data sources:
  - Predicted lineups (before match) via GraphQL API from ds.lsapp.eu
  - Official lineups (after team announcement) via same API  
  - Player ratings (after match) from match statistics
  - Injuries/Absentees from team data

Usage:
    from api.scraper import FlashscoreScraper
    scraper = FlashscoreScraper()
    data = scraper.get_match_data("brazil-I9l9aqLq/morocco-IDKYO3R8")
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))

from playwright.sync_api import sync_playwright


class FlashscoreScraper:
    """Scrape Flashscore match pages for lineups, formations, and player data."""

    def __init__(self, headless=True, timeout=30000):
        self.headless = headless
        self.timeout = timeout

    def get_match_data(self, match_slug: str) -> dict:
        """Fetch match data including lineups from Flashscore.

        Args:
            match_slug: e.g. "brazil-I9l9aqLq/morocco-IDKYO3R8" or full URL
                       or "/match/football/..." (relative from search_match)

        Returns:
            dict with lineups, formations, injuries
        """
        if match_slug.startswith("http"):
            url = match_slug.rstrip("/") + "/"
        elif match_slug.startswith("/match/"):
            url = f"https://www.flashscore.com{match_slug.rstrip('/')}/"
        else:
            url = f"https://www.flashscore.com/match/football/{match_slug.strip('/')}/"
        return self._fetch(url)

    def search_match(self, home_team: str, away_team: str) -> list[dict]:
        """Search Flashscore football page for matching matches."""
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1920, "height": 1080}, locale="en-US",
            )
            page = context.new_page()
            page.goto("https://www.flashscore.com/football/",
                      wait_until="domcontentloaded", timeout=self.timeout)
            page.wait_for_timeout(3000)
            links = page.locator("a[href*='/match/']").all()
            for link in links:
                href = link.get_attribute("href") or ""
                text = link.text_content() or ""
                if home_team.lower() in text.lower() or away_team.lower() in text.lower():
                    results.append({"url": href, "text": text.strip()})
            browser.close()
        return results

    def _fetch(self, url: str) -> dict:
        """Load page via Playwright and extract data from GraphQL responses."""
        result = {"url": url, "home_team": None, "away_team": None,
                  "formations": {}, "starting_xi": {}, "substitutes": {},
                  "injuries": [], "notes": []}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1920, "height": 1080}, locale="en-US",
            )
            page = context.new_page()
            captured = {}

            def on_response(response):
                rurl = response.url
                if "graphql" in rurl:
                    try:
                        captured[rurl] = response.json()
                    except Exception:
                        pass

            page.on("response", on_response)

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                page.wait_for_timeout(2000)
                try:
                    tab = page.locator("text=LINEUPS").first
                    if tab.is_visible(timeout=3000):
                        tab.click()
                        page.wait_for_timeout(2000)
                except Exception:
                    pass
            except Exception as e:
                result["notes"].append(f"Page load error: {e}")

            browser.close()

        self._parse_apis(captured, result)
        return result

    def _parse_apis(self, apis: dict, result: dict):
        """Extract data from captured GraphQL responses."""
        for data in apis.values():
            event = data.get("data", {}).get("findEventById")
            if not event:
                continue

            participants = event.get("eventParticipants", [])
            home_found = False
            away_found = False

            for team in participants:
                team_name = team.get("name", "")
                side = team.get("type", {}).get("side")

                if side == "HOME":
                    result["home_team"] = team_name
                    home_found = True
                elif side == "AWAY":
                    result["away_team"] = team_name
                    away_found = True

                predicted = team.get("predictedLineup")
                if predicted:
                    self._parse_predicted_lineup(predicted, team_name, result)

                injuries = team.get("injuries", [])
                if injuries:
                    for inj in injuries:
                        result["injuries"].append({
                            "team": team_name,
                            "player": inj.get("name", ""),
                            "reason": inj.get("reason", ""),
                        })

            # Fallback: assign by position order
            if not home_found and not away_found and len(participants) >= 2:
                result["home_team"] = participants[0].get("name", "")
                result["away_team"] = participants[1].get("name", "")
            elif not home_found and not away_found and len(participants) == 1:
                result["home_team"] = participants[0].get("name", "")

    def _parse_predicted_lineup(self, predicted: dict, team_name: str, result: dict):
        """Extract players and formation."""
        formation = predicted.get("formation", {})
        formation_name = formation.get("name", "") if formation else ""
        if formation_name:
            result["formations"][team_name] = formation_name

        players = predicted.get("players", [])
        groups = predicted.get("groups", [])
        starting = []
        bench = []

        # Build formation position map from rows
        # row 0 = GK, row 1 = defense, row 2 = midfield, etc.
        pos_map = {}  # player_id -> row_index
        lines = formation.get("lines", []) if formation else []
        for line in lines:
            rows = line.get("rows", [])
            for row in rows:
                row_key = row.get("sortKey", 0)
                for pid in row.get("playerIds", []):
                    pos_map[pid] = row_key

        if groups:
            for group in groups:
                gname = group.get("name", "").lower()
                pids = set(group.get("playerIds", []))
                is_starting = "starting" in gname or "expected" in gname
                for p in players:
                    if p.get("id") in pids:
                        player = self._extract_player(p, pos_map)
                        if is_starting:
                            starting.append(player)
                        else:
                            bench.append(player)
        else:
            for p in players:
                starting.append(self._extract_player(p, pos_map))

        result["starting_xi"][team_name] = starting
        result["substitutes"][team_name] = bench

    def _extract_player(self, p: dict, pos_map: dict = None) -> dict:
        """Extract player info, derive position from formation row."""
        row = (pos_map or {}).get(p.get("id"))
        pos_labels = {0: "GK", 1: "DEF", 2: "MID", 3: "FWD", 4: "FWD"}
        position = pos_labels.get(row, "")

        player = {
            "id": p.get("id", ""),
            "name": p.get("fieldName", p.get("listName", "")),
            "number": p.get("number", ""),
            "position": position,
        }
        participant = p.get("participant", {})
        if participant and isinstance(participant, dict):
            for key in ("age", "height", "marketValue"):
                val = participant.get(key)
                if val is not None:
                    player[key] = val
        return player


if __name__ == "__main__":
    import sys
    slug = sys.argv[1] if len(sys.argv) > 1 else "brazil-I9l9aqLq/morocco-IDKYO3R8"
    scraper = FlashscoreScraper()

    if sys.argv[1:2] == ["search"] and len(sys.argv) >= 4:
        results = scraper.search_match(sys.argv[2], sys.argv[3])
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        data = scraper.get_match_data(slug)
        print(json.dumps(data, ensure_ascii=False, indent=2))
