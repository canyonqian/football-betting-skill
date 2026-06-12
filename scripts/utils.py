"""Shared utilities for rate limiting, retry, and output formatting."""

import time
import json
from typing import Any


class RateLimitError(Exception):
    """Raised when API rate limit is hit."""


def print_json(data: Any) -> None:
    """Print data as formatted JSON to stdout for agent consumption."""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def implied_probability(decimal_odds: float) -> float:
    """Convert decimal odds to implied probability (0-1)."""
    return 1.0 / decimal_odds


def odds_to_fair_value(decimal_odds: float, overround: float = 0.07) -> float:
    """Remove estimated overround from odds to get fair value probability."""
    raw = implied_probability(decimal_odds)
    return raw / (1.0 + overround)


def value_score(fair_prob: float, decimal_odds: float) -> float:
    """Calculate value score: positive = value bet. fair_prob * odds - 1."""
    return fair_prob * decimal_odds - 1.0


def collect_errors(results: list[dict]) -> list[str]:
    """Extract error messages from sub-agent result list."""
    return [r["error"] for r in results if "error" in r]
