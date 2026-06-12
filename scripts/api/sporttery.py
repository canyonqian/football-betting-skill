"""竞彩网 (Sporttery.cn) API client — Chinese government lottery odds.

Provides match listings, 1X2 odds (胜平负), Asian handicap (让球),
correct score (比分), and half-time/full-time (半全场) for all
竞彩 football coverage including World Cup.

No API key required. Unlimited requests.
"""

import requests
from typing import Any, Optional
from datetime import datetime, timezone

BASE_URL = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry"


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://m.sporttery.cn/mjc/jsq/zqhhgg/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def _fetch() -> list[dict]:
    """Fetch all match days from 竞彩网."""
    resp = requests.get(BASE_URL, params={"channel": "c"}, headers=_HEADERS, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"sporttery.cn returned {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"sporttery.cn API error: {data.get('errorMessage', 'unknown')}")
    return data.get("value", {}).get("matchInfoList", [])


def _parse_sporttery_odds(match: dict) -> dict:
    """Parse a single match entry into a standardised format."""
    return {
        "match_id": match.get("matchId"),
        "match_num": match.get("matchNumStr", ""),
        "league": {
            "name": match.get("leagueAbbName", ""),
            "full_name": match.get("leagueAllName", ""),
            "code": match.get("leagueCode", ""),
        },
        "home_team": match.get("homeTeamAllName", ""),
        "away_team": match.get("awayTeamAllName", ""),
        "home_rank": match.get("homeRank", ""),
        "away_rank": match.get("awayRank", ""),
        "match_date": match.get("matchDate", ""),
        "match_time": match.get("matchTime", ""),
        "match_status": match.get("matchStatus", ""),
        "odds": {
            "h2h": _parse_had(match.get("had")),
            "asian_handicap": _parse_hhad(match.get("hhad")),
            "correct_score": _parse_crs(match.get("crs")),
            "half_time_full_time": _parse_hafu(match.get("hafu")),
        },
    }


def _parse_had(had: Optional[dict]) -> Optional[dict]:
    if not had:
        return None
    return {
        "home": float(had["h"]) if had.get("h") else None,
        "draw": float(had["d"]) if had.get("d") else None,
        "away": float(had["a"]) if had.get("a") else None,
        "updated": f"{had.get('updateDate', '')} {had.get('updateTime', '')}",
    }


def _parse_hhad(hhad: Optional[dict]) -> Optional[dict]:
    if not hhad or not hhad.get("goalLine"):
        return None
    return {
        "home": float(hhad["h"]) if hhad.get("h") else None,
        "draw": float(hhad["d"]) if hhad.get("d") else None,
        "away": float(hhad["a"]) if hhad.get("a") else None,
        "goal_line": hhad.get("goalLine", ""),
        "goal_line_value": hhad.get("goalLineValue", ""),
        "updated": f"{hhad.get('updateDate', '')} {hhad.get('updateTime', '')}",
    }


def _parse_crs(crs: Optional[dict]) -> Optional[dict]:
    if not crs:
        return None
    scores = {}
    for key, val in crs.items():
        if key in ("updateDate", "updateTime", "goalLine", "goalLineValue"):
            continue
        if val and str(val).replace(".", "").isdigit():
            parts = key.replace("s", "").split("s")
            if len(parts) == 2:
                try:
                    h, a = int(parts[0]), int(parts[1])
                    scores[f"{h}-{a}"] = float(val)
                except ValueError:
                    pass
    return {
        "scores": scores,
        "updated": f"{crs.get('updateDate', '')} {crs.get('updateTime', '')}",
    }


def _parse_hafu(hafu: Optional[dict]) -> Optional[dict]:
    if not hafu:
        return None
    result = {}
    mapping = {
        "hh": "Home/Home", "hd": "Home/Draw", "ha": "Home/Away",
        "dh": "Draw/Home", "dd": "Draw/Draw", "da": "Draw/Away",
        "ah": "Away/Home", "ad": "Away/Draw", "aa": "Away/Away",
    }
    for key, label in mapping.items():
        if key in hafu and hafu[key]:
            result[label] = float(hafu[key])
    return {
        "odds": result,
        "updated": f"{hafu.get('updateDate', '')} {hafu.get('updateTime', '')}",
    }


def search_by_teams(home_team: str, away_team: str) -> Optional[dict]:
    """Search for a match by team names (fuzzy match)."""
    days = _fetch()
    for day in days:
        for sub in day.get("subMatchList", []):
            h = sub.get("homeTeamAllName", "")
            a = sub.get("awayTeamAllName", "")
            if (home_team.lower() in h.lower() and away_team.lower() in a.lower()):
                return _parse_sporttery_odds(sub)
            if (home_team.lower() in a.lower() and away_team.lower() in h.lower()):
                sub["homeTeamAllName"], sub["awayTeamAllName"] = sub["awayTeamAllName"], sub["homeTeamAllName"]
                sub["homeTeamAbbName"], sub["awayTeamAbbName"] = sub["awayTeamAbbName"], sub["homeTeamAbbName"]
                if "had" in sub and sub["had"]:
                    sub["had"]["h"], sub["had"]["a"] = sub["had"]["a"], sub["had"]["h"]
                if "hhad" in sub and sub["hhad"]:
                    gl = sub["hhad"].get("goalLineValue", "0")
                    try:
                        val = float(gl)
                        sub["hhad"]["goalLineValue"] = str(-val)
                        if val > 0:
                            sub["hhad"]["goalLine"] = f"+{int(-val)}"
                        else:
                            sub["hhad"]["goalLine"] = str(int(-val))
                    except ValueError:
                        pass
                    sub["hhad"]["h"], sub["hhad"]["a"] = sub["hhad"]["a"], sub["hhad"]["h"]
                return _parse_sporttery_odds(sub)
    return None


def get_all_matches() -> list[dict]:
    """Get all matches from all available days."""
    result = []
    days = _fetch()
    for day in days:
        for sub in day.get("subMatchList", []):
            result.append(_parse_sporttery_odds(sub))
    return result


def get_world_cup_matches() -> list[dict]:
    """Get all World Cup matches."""
    result = []
    days = _fetch()
    for day in days:
        for sub in day.get("subMatchList", []):
            code = sub.get("leagueCode", "")
            if code == "WCC":
                result.append(_parse_sporttery_odds(sub))
    return result
