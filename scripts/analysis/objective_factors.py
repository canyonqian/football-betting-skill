"""Sub-Agent F: Objective Factors Analysis (football-data.org edition).

Identifies match-changing variables beyond form and odds:
- League position from standings
- Recent form from standings
- Squad size from team endpoint
- Fatigue indicators from recent match congestion
- Provides search queries for agent to find injury/team news

Usage:
    python objective_factors.py <match_id> <competition_id> <season>
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.football_data import get_match, get_standings, get_team, get_matches
from utils import print_json


def _find_team_in_standings(standings: list[dict], team_id: int) -> dict | None:
    for standing_group in standings:
        table = standing_group.get("table", [])
        for row in table:
            if row.get("team", {}).get("id") == team_id:
                return row
    return None


def _form_points(form_str: str, n: int = 5) -> int:
    if not form_str:
        return 0
    pts = 0
    for c in form_str[:n]:
        if c == "W":
            pts += 3
        elif c == "D":
            pts += 1
    return pts


def _assess_fatigue(team_id: int, competition_id: str, match_date_str: str) -> dict:
    """Count recent completed matches in same competition before the fixture date."""
    try:
        match_date = datetime.fromisoformat(match_date_str.replace("Z", "+00:00"))
        date_to = match_date.strftime("%Y-%m-%d")
        matches = get_matches(competition_id=competition_id, date_to=date_to, status="FINISHED")
    except Exception:
        return {}

    team_matches = [
        m for m in matches
        if m.get("homeTeam", {}).get("id") == team_id
        or m.get("awayTeam", {}).get("id") == team_id
    ]

    team_matches.sort(key=lambda m: m.get("utcDate", ""), reverse=True)
    recent = team_matches[:10]

    played = len(recent)

    if played >= 2:
        dates = []
        for m in recent:
            ds = m.get("utcDate", "")
            if ds:
                try:
                    dates.append(datetime.fromisoformat(ds.replace("Z", "+00:00")))
                except (ValueError, TypeError):
                    pass
        if len(dates) >= 2:
            span_days = (dates[0] - dates[-1]).days
            density = played / max(span_days, 1)
        else:
            density = None
    else:
        density = None

    return {
        "recent_matches": played,
        "match_density": round(density, 3) if density else None,
    }


def run(match_id: int, competition_id: str, season: int) -> dict:
    match = get_match(match_id)
    if not match:
        return {"agent": "objective_factors", "match_id": match_id,
                "error": "Match not found"}

    home = match.get("homeTeam", {})
    away = match.get("awayTeam", {})
    home_id = home.get("id")
    away_id = away.get("id")
    home_name = home.get("name", home.get("shortName", "Home"))
    away_name = away.get("name", away.get("shortName", "Away"))
    match_date_str = match.get("utcDate", "")

    # ── Standings ──────────────────────────────────────────────────
    try:
        standings = get_standings(competition_id, season=season)
    except Exception:
        standings = []

    home_row = _find_team_in_standings(standings, home_id)
    away_row = _find_team_in_standings(standings, away_id)

    home_pos = home_row.get("position") if home_row else None
    away_pos = away_row.get("position") if away_row else None
    home_form = (home_row.get("form", "") or "") if home_row else ""
    away_form = (away_row.get("form", "") or "") if away_row else ""

    # ── Squad size ─────────────────────────────────────────────────
    home_squad = 0
    away_squad = 0
    try:
        if home_id:
            ht = get_team(home_id)
            home_squad = len(ht.get("squad", []))
    except Exception:
        pass
    try:
        if away_id:
            at = get_team(away_id)
            away_squad = len(at.get("squad", []))
    except Exception:
        pass

    # ── Fatigue ────────────────────────────────────────────────────
    home_fatigue = _assess_fatigue(home_id, competition_id, match_date_str) if home_id else {}
    away_fatigue = _assess_fatigue(away_id, competition_id, match_date_str) if away_id else {}

    # ── Build notes & signal ───────────────────────────────────────
    notes = []
    home_pts = _form_points(home_form)
    away_pts = _form_points(away_form)

    if home_pos is not None and away_pos is not None:
        gap = away_pos - home_pos
        if gap > 5:
            notes.append(f"{home_name} ({home_pos}{_ordinal(home_pos)}) much higher in table than {away_name} ({away_pos}{_ordinal(away_pos)})")
        elif gap > 0:
            notes.append(f"{home_name} ({home_pos}{_ordinal(home_pos)}) above {away_name} ({away_pos}{_ordinal(away_pos)}) in table")
        elif gap < -5:
            notes.append(f"{away_name} ({away_pos}{_ordinal(away_pos)}) much higher in table than {home_name} ({home_pos}{_ordinal(home_pos)})")
        elif gap < 0:
            notes.append(f"{away_name} ({away_pos}{_ordinal(away_pos)}) above {home_name} ({home_pos}{_ordinal(home_pos)}) in table")

    if home_form:
        notes.append(f"{home_name} recent form: {home_form[:5]} ({home_pts} pts / last 5)")
    if away_form:
        notes.append(f"{away_name} recent form: {away_form[:5]} ({away_pts} pts / last 5)")

    if home_pts >= 10 and away_pts <= 3:
        notes.append(f"Strong recent-form gap favoring {home_name}")
    elif away_pts >= 10 and home_pts <= 3:
        notes.append(f"Strong recent-form gap favoring {away_name}")

    if home_squad > 0 and away_squad > 0:
        if abs(home_squad - away_squad) >= 5:
            bigger = home_name if home_squad > away_squad else away_name
            smaller = away_name if home_squad > away_squad else home_name
            notes.append(f"{bigger} squad ({max(home_squad, away_squad)}) notably larger than {smaller} ({min(home_squad, away_squad)})")

    if home_fatigue.get("recent_matches"):
        notes.append(f"{home_name} recent match load: {home_fatigue['recent_matches']} matches (density {home_fatigue.get('match_density', 'N/A')}/day)")
    if away_fatigue.get("recent_matches"):
        notes.append(f"{away_name} recent match load: {away_fatigue['recent_matches']} matches (density {away_fatigue.get('match_density', 'N/A')}/day)")

    notes.append("Injury data not available via API. Search sportsmole.co.uk or dongqiudi.com for team news.")

    search_queries = [
        f"{home_name} injuries suspensions {season}-{season + 1}",
        f"{away_name} injuries suspensions {season}-{season + 1}",
    ]

    # ── Signal strength ────────────────────────────────────────────
    pos_signal = (home_pos is not None and away_pos is not None
                  and abs(away_pos - home_pos) > 5)
    form_signal = abs(home_pts - away_pts) >= 7
    signals = sum([pos_signal, form_signal])

    if signals >= 2:
        strength = "strong"
    elif signals >= 1:
        strength = "medium"
    else:
        strength = "weak"

    # ── Finding ────────────────────────────────────────────────────
    parts = []
    if pos_signal:
        higher = home_name if (home_pos or 0) < (away_pos or 0) else away_name
        parts.append(f"{higher} has significant table-position advantage")
    if form_signal:
        in_form = home_name if home_pts > away_pts else away_name
        parts.append(f"{in_form} in stronger recent form")

    finding = "Objective factors: " + ("; ".join(parts) if parts else "No clear objective advantage for either side")

    return {
        "agent": "objective_factors",
        "fixture": f"{home_name} vs {away_name}",
        "finding": finding,
        "signal_strength": strength,
        "key_metrics": {
            "home": {
                "team_id": home_id,
                "league_position": home_pos,
                "recent_form": home_form[:5] if home_form else None,
            },
            "away": {
                "team_id": away_id,
                "league_position": away_pos,
                "recent_form": away_form[:5] if away_form else None,
            },
        },
        "notes": notes,
        "search_queries": search_queries,
    }


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print_json({"error": "Usage: objective_factors.py <match_id> <competition_id> <season>"})
        sys.exit(1)
    mi = int(sys.argv[1])
    ci = sys.argv[2]
    se = int(sys.argv[3])
    try:
        result = run(mi, ci, se)
        print_json(result)
    except Exception as e:
        print_json({"agent": "objective_factors", "match_id": mi, "error": str(e)})
