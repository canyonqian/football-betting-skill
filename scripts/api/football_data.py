"""Football-Data.org v4 client — fixtures, results, standings, H2H.

Requires FOOTBALL_DATA_KEY environment variable.
Free tier: 10 req/min, 12 competitions, no live scores.
Register at: https://www.football-data.org/client/register
"""

import os
import time
import requests
from typing import Any, Optional

BASE_URL = "https://api.football-data.org/v4"


def _headers() -> dict[str, str]:
    key = os.environ.get("FOOTBALL_DATA_KEY", "")
    if not key:
        raise RuntimeError("FOOTBALL_DATA_KEY environment variable not set")
    return {"X-Auth-Token": key}


def _get(endpoint: str, params: Optional[dict[str, Any]] = None, retries: int = 2) -> dict:
    url = f"{BASE_URL}/{endpoint}"

    for attempt in range(retries + 1):
        resp = requests.get(url, headers=_headers(), params=params or {}, timeout=30)

        if resp.status_code == 429:
            if attempt < retries:
                # Per-minute limit — wait and retry
                delay = 15 * (attempt + 1)
                time.sleep(delay)
                continue
            raise RuntimeError(
                "Football-Data.org rate limit reached after retries. "
                "Wait 1 minute or upgrade plan for more requests."
            )

        if resp.status_code == 403:
            body = resp.text[:300]
            raise RuntimeError(
                f"Football-Data.org returned 403 (restricted): {body}"
            )

        if resp.status_code == 404:
            raise RuntimeError(f"Football-Data.org resource not found: {url}")

        if resp.status_code != 200:
            body = resp.text[:300]
            raise RuntimeError(
                f"Football-Data.org returned {resp.status_code}: {body}"
            )

        data = resp.json()

        # Check for error in response body (e.g. 400 with JSON error)
        if isinstance(data, dict) and "error" in data:
            if resp.status_code >= 400:
                raise RuntimeError(f"API error: {data['error']}")

        # Pre-sleep if running low on rate limit
        remaining = resp.headers.get("X-RequestsAvailable")
        if remaining and remaining.isdigit() and int(remaining) <= 2 and attempt == 0:
            reset_secs = resp.headers.get("X-RequestCounter-Reset")
            if reset_secs and reset_secs.isdigit():
                time.sleep(int(reset_secs) + 1)
            else:
                time.sleep(60)

        return data

    raise RuntimeError("Football-Data.org rate limit exhausted.")


def get_matches(
    competition_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    matchday: Optional[int] = None,
    status: Optional[str] = None,
) -> list[dict]:
    """List matches. If competition_id is given, uses the competition subresource.

    Args:
        competition_id: Competition code (e.g. 'PL') or numeric id.
        date_from: YYYY-MM-DD start of range.
        date_to: YYYY-MM-DD end of range (exclusive).
        matchday: Matchday number.
        status: SCHEDULED | TIMED | IN_PLAY | PAUSED | FINISHED | POSTPONED | CANCELLED.
    """
    params: dict[str, Any] = {}
    if date_from:
        params["dateFrom"] = date_from
    if date_to:
        params["dateTo"] = date_to
    if matchday is not None:
        params["matchday"] = matchday
    if status:
        params["status"] = status

    if competition_id:
        endpoint = f"competitions/{competition_id}/matches"
    else:
        endpoint = "matches"

    return _get(endpoint, params).get("matches", [])


def get_match(match_id: int) -> dict:
    """Get a single match with full details (lineups, goals, bookings, stats, odds)."""
    return _get(f"matches/{match_id}")


def get_head2head(match_id: int) -> dict:
    """Get head-to-head history for the two teams involved in a match.

    Returns previous encounters between the same two teams.
    """
    return _get(f"matches/{match_id}/head2head")


def get_standings(
    competition_id: str,
    season: Optional[int] = None,
    matchday: Optional[int] = None,
    date: Optional[str] = None,
) -> list[dict]:
    """Get league standings for a competition.

    Args:
        competition_id: Competition code (e.g. 'PL') or numeric id.
        season: 4-digit start year (e.g. 2024).
        matchday: Matchday number for historical standings at that point.
        date: YYYY-MM-DD for standings on a specific date.
    """
    params: dict[str, Any] = {}
    if season is not None:
        params["season"] = season
    if matchday is not None:
        params["matchday"] = matchday
    if date:
        params["date"] = date

    return _get(f"competitions/{competition_id}/standings", params).get("standings", [])


def get_team(team_id: int) -> dict:
    """Get team information including current squad, coach, and running competitions."""
    return _get(f"teams/{team_id}")


def get_competitions() -> list[dict]:
    """List all competitions available to the authenticated client."""
    return _get("competitions").get("competitions", [])
