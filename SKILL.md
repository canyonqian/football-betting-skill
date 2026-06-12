---
name: football-betting-analysis
description: Use when the user wants to analyse football matches for betting purposes — covers 1X2, Asian handicap, and Over/Under markets. Use when the user asks for 比赛分析, 足彩分析, 盘口分析, 赔率分析, or wants to understand bookmaker pricing logic. Launches 8 parallel sub-agents for multi-dimensional analysis, then cross-validates to find value opportunities.
---

# Football Betting Analysis Skill

## Overview

Reverse-engineer bookmaker pricing logic through 8 parallel analysis dimensions. Find the gap between what odds say and what fundamentals/statistics/history suggest — that gap is where betting value lives.

**Language rule:** All internal reasoning is in English. Output to the user in their language.

**Core principle:** Not predicting results. Finding mispricing.

## When to Use

- User asks to analyse a football match for betting
- User wants 1X2 / Asian handicap / over-under analysis
- User asks for match predictions with odds context
- User wants to understand bookmaker intent from odds movement

**Required:** User must provide fixture ID, league ID, and season, OR enough context to look them up (team names + league name).

## Architecture

```
User request: "Analyze fixture_id=X, league_id=Y, season=Z"
  → Master agent (you): spawn 8 parallel sub-agents
    ├── A: fundamentals.py      (form/H2H/standings vs odds gap)
    ├── B: odds_signals.py       (odds movement & bookmaker intent)
    ├── C: historical_backtest.py(odds pattern backtesting)
    ├── D: bookmaker_divergence.py(multi-bookmaker dispersion)
    ├── E: market_sentiment.py   (public bias & contrarian signals)
    ├── F: objective_factors.py  (injuries, fatigue, squad depth)
    ├── G: tactical_matchup.py   (formations, style clash, goal timing)
    └── H: player_coach_xg.py    (player impact, coach profile, xG proxy)
  → Wait for ALL 8 to complete
  → Feed results to aggregator for cross-validation
  → Present final report to user
```

## Execution Protocol

### Step 0: Verify API Key

**BEFORE any analysis, verify `RAPIDAPI_KEY` is set:**

```bash
if (-not $env:RAPIDAPI_KEY) { Write-Output "ERROR: RAPIDAPI_KEY environment variable not set. Please configure it first."; exit 1 }
python -c "from scripts.api.api_football import _headers; print('API key configured: OK')"
```

If not configured, **STOP and tell the user:**
> "RAPIDAPI_KEY not configured. Get a free key at https://rapidapi.com/api-sports/api/api-football and set it with: `set RAPIDAPI_KEY=your_key_here`"

**Do NOT proceed without an API key.** Every sub-agent depends on it.

Get a free key at https://rapidapi.com/api-sports/api/api-football — no credit card required for the free tier (100 requests/day). To upgrade for more requests, subscribe to a paid plan on the same page.

### Step 1: Parse the user request

The user may provide:
- `fixture_id` directly
- Team names and league (you must look up IDs first)
- A URL or reference to a specific match

If IDs are missing, use the API to search for them before proceeding.

### Step 2: Launch 8 sub-agents in PARALLEL

Use the Task tool to spawn 8 sub-agents simultaneously. Each sub-agent runs one analysis script:

```
Task 1 (fundamentals): 
  Run: python scripts/analysis/fundamentals.py <fixture_id> <league_id> <season>
  Reads JSON output from stdout. Returns the parsed dict.

Task 2 (odds_signals):
  Run: python scripts/analysis/odds_signals.py <fixture_id> <league_id> <season>

Task 3 (historical_backtest):
  Run: python scripts/analysis/historical_backtest.py <fixture_id> <league_id> <season>

Task 4 (bookmaker_divergence):
  Run: python scripts/analysis/bookmaker_divergence.py <fixture_id> <league_id> <season>

Task 5 (market_sentiment):
  Run: python scripts/analysis/market_sentiment.py <fixture_id> <league_id> <season>

Task 6 (objective_factors):
  Run: python scripts/analysis/objective_factors.py <fixture_id> <league_id> <season>

Task 7 (tactical_matchup):
  Run: python scripts/analysis/tactical_matchup.py <fixture_id> <league_id> <season>

Task 8 (player_coach_xg):
  Run: python scripts/analysis/player_coach_xg.py <fixture_id> <league_id> <season>
```

**CRITICAL RULES:**
- All 8 sub-agents MUST be launched in parallel — NOT sequentially
- Sub-agents are information-isolated — they do NOT share context or see each other's output
- Each sub-agent returns JSON to stdout. Capture it.
- If any sub-agent returns an error, record it and continue. A partial analysis is better than none.
- Each sub-agent script requires `RAPIDAPI_KEY` in environment variables
- For xG analysis (agent H), optionally install: `pip install soccerdata`

### Step 3: Run the aggregator

After all 8 sub-agents complete, feed their collected JSON results to the aggregator:

```
Run: python scripts/aggregator.py <subagent_results.json>
```

Or apply the cross-validation logic from `aggregator.py` directly in your reasoning.

### Step 4: Present the final report

**Output language must match the user's language.** If the user asked in Chinese, respond in Chinese. If in English, respond in English. The report structure is:

1. **Summary**: One-line overall assessment
2. **Conflicts & Consensus**: Which dimensions disagree (conflicts) and which agree (consensus) — conflicts are the most interesting findings
3. **Agent-by-agent findings**: Brief summary of each sub-agent's key output
4. **Betting recommendations**: Per bet type — Recommend / Watch / Avoid with reasoning
5. **Risk warnings**: Key risk factors the user should know

### Reading Odds Movement
- **Opening → current direction**: If odds shorten on a side, money is flowing that way
- **Sharp move late**: Big shift in last hours before kickoff = strongest signal
- **Opposite movement**: If odds move against popular opinion, bookmaker is likely right

### Reading Bookmaker Intent
- **Deep handicap (≥1 ball)**: Bookmaker expects a clear result
- **Shallow handicap (≤0.25 ball)**: Bookmaker sees a toss-up
- **Line upgrade/downgrade**: Bookmaker adjusting risk exposure
- **Return rate**: Low = efficient market, high = wide margin (less signal)

### Reading Tactical Styles
- **Formation counters**: 3-5-2 exploits 4-3-3 wide areas; 4-2-3-1 #10 finds gaps between midfield lines
- **Possession vs Counter**: High possession teams vulnerable to quick transitions; low block teams struggle against sustained pressure
- **Early vs Late scoring**: Teams that score early but concede late may drop points despite dominating
- **Pressing intensity**: High press teams (>20 tackles/game) disrupt possession teams; low press invites pressure

### Using xG (Expected Goals)
- Install soccerdata for real xG: `pip install soccerdata`
- xG > actual goals = wasteful finishing, likely to regress
- xG < actual goals = clinical finishing, may be unsustainable
- Large xG discrepancy (5+ matches) = strongest signal for over/under bets

### Contrarian Indicators
- Public heavily on one side + odds NOT moving = bookmaker confident, traps being set
- Sharp bookmakers (Pinnacle) disagree with retail (Bet365) = follow the sharps
- Market overheating on favorite + fundamentals disagree = potential value on underdog

## API Setup

Before analysis, ensure:
```bash
set RAPIDAPI_KEY=your_key_here
```

Get an API key from: https://rapidapi.com/api-sports/api/api-football
Sign up for the free tier (100 requests/day). No credit card required.

**If rate limit is hit:** Report the error clearly. User can upgrade their plan for more requests.

## Looking Up IDs

When user provides team names instead of IDs:

```bash
# Search for league ID
python -c "from scripts.api.api_football import get_leagues; from scripts.utils import print_json; print_json(get_leagues(search='World Cup'))"

# Search for team ID  
python -c "from scripts.api.api_football import get_teams; from scripts.utils import print_json; print_json(get_teams(name='Brazil'))"

# Find fixtures
python -c "from scripts.api.api_football import get_fixtures; from scripts.utils import print_json; print_json(get_fixtures(league_id=X, season=2026, team_id=Y))"
```

## Quick Reference: Common League IDs

| Competition | League ID | Common Seasons |
|------------|-----------|----------------|
| World Cup | 1 | 2022, 2026 |
| UEFA Euro | 4 | 2024, 2028 |
| Premier League | 39 | 2022, 2023, 2024, 2025 |
| La Liga | 140 | 2022, 2023, 2024, 2025 |
| Bundesliga | 78 | 2022, 2023, 2024, 2025 |
| Serie A | 135 | 2022, 2023, 2024, 2025 |
| Ligue 1 | 61 | 2022, 2023, 2024, 2025 |
| Champions League | 2 | 2022, 2023, 2024, 2025 |
| CSL | 169 | 2022, 2023, 2024, 2025 |
| J-League | 98 | 2022, 2023, 2024, 2025 |
