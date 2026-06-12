---
name: football-betting-analysis
description: Use when the user wants to analyse football matches for betting purposes — covers 1X2, Asian handicap, and Over/Under markets. Use when the user asks for 比赛分析, 足彩分析, 盘口分析, 赔率分析, or wants to understand bookmaker pricing logic. Launches 6 parallel sub-agents for multi-dimensional analysis, then cross-validates to find value opportunities.
---

# Football Betting Analysis Skill

## Overview

Reverse-engineer bookmaker pricing logic through 6 parallel analysis dimensions. Find the gap between what odds say and what fundamentals/statistics/history suggest — that gap is where betting value lives.

**Core principle:** Not predicting results. Finding mispricing.

## When to Use

- User asks to analyse a football match for betting
- User wants 欧赔/亚盘/大小球 analysis
- User asks "这场比赛怎么看" for betting purposes
- User wants to understand bookmaker intent from odds movement

**Required:** User must provide fixture ID, league ID, and season, OR enough context to look them up (team names + league name).

## Architecture

```
User request: "分析 fixture_id=X, league_id=Y, season=Z"
  → Master agent (you): spawn 6 parallel sub-agents
    ├── Sub-agent A: fundamentals.py (基本面 vs 盘口偏差)
    ├── Sub-agent B: odds_signals.py (盘口信号解读)
    ├── Sub-agent C: historical_backtest.py (历史同赔回测)
    ├── Sub-agent D: bookmaker_divergence.py (庄家分歧度)
    ├── Sub-agent E: market_sentiment.py (市场情绪)
    └── Sub-agent F: objective_factors.py (客观因素)
  → Wait for ALL 6 to complete
  → Feed results to aggregator.py for cross-validation
  → Present final report to user
```

## Execution Protocol

### Step 1: Parse the user request

The user may provide:
- `fixture_id` directly
- Team names and league (you must look up IDs first)
- A URL or reference to a specific match

If IDs are missing, use the API to search for them before proceeding.

### Step 2: Launch 6 sub-agents in PARALLEL

Use the Task tool to spawn 6 sub-agents simultaneously. Each sub-agent runs one analysis script:

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
```

**CRITICAL RULES:**
- All 6 sub-agents MUST be launched in parallel — NOT sequentially
- Sub-agents are information-isolated — they do NOT share context or see each other's output
- Each sub-agent returns JSON to stdout. Capture it.
- If any sub-agent returns an error, record it and continue. A partial analysis is better than none.
- Each sub-agent script requires `RAPIDAPI_KEY` in environment variables

### Step 3: Run the aggregator

After all 6 sub-agents complete, feed their collected JSON results to the aggregator:

```
Run: python scripts/aggregator.py <subagent_results.json>
```

Or apply the cross-validation logic from `aggregator.py` directly in your reasoning.

### Step 4: Present the final report

Format the output clearly for the user:

1. **摘要**: One-line summary of the analysis
2. **矛盾与一致**: Which dimensions conflict, which agree
3. **各维度详情**: Brief summary of each sub-agent's key findings
4. **投注建议**: Per bet type: Recommend / Watch / Avoid with reasons
5. **风险提示**: Key risk factors

## API Setup

Before analysis, ensure:
```bash
set RAPIDAPI_KEY=your_key_here
```

Get an API key from: https://rapidapi.com/api-sports/api/api-football
Sign up for the free tier (100 requests/day).

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

## Key Analysis Concepts

### Reading Odds Movement
- **初盘→即时盘 direction**: If odds shorten on a side, money is flowing that way
- **Sharp move late**: Big shift in last hours before kickoff = strongest signal
- **Opposite movement**: If odds move against popular opinion, bookmaker is likely right

### Reading Bookmaker Intent
- **Deep handicap (≥1 ball)**: Bookmaker expects a clear result
- **Shallow handicap (≤0.25 ball)**: Bookmaker sees a toss-up
- **Line upgrade/downgrade**: Bookmaker adjusting risk exposure
- **Return rate**: Low = efficient market, high = wide margin (less signal)

### Contrarian Indicators
- Public heavily on one side + odds NOT moving = bookmaker confident, traps being set
- Sharp bookmakers (Pinnacle) disagree with retail (Bet365) = follow the sharps
- Market overheating on favorite + fundamentals disagree = potential value on underdog

## Output Format

Final report follows this structure:
```
📊 比赛: [Home] vs [Away] | [Date]
━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 六维分析摘要:
  [fundamentals]: [finding] (信号强度: strong/medium/weak)
  [odds_signals]: [finding] (信号强度: ...)
  ...

⚠️ 矛盾点 (Conflicts):
  - [conflict description] → [interpretation]

✅ 一致点 (Consensus):
  - [agreement description]

🎯 投注建议:
  胜平负:     Recommend/Watch/Avoid — [reasoning]
  让球盘:     Recommend/Watch/Avoid — [reasoning]
  大小球:     Recommend/Watch/Avoid — [reasoning]

📋 风险提示:
  - [risk factor 1]
  - [risk factor 2]
```

## Quick Reference: Common World Cup IDs

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
| CSL (中超) | 169 | 2022, 2023, 2024, 2025 |
| J-League | 98 | 2022, 2023, 2024, 2025 |
