---
name: football-betting-analysis
description: Use when the user wants to predict, analyze, or evaluate football/soccer matches — including match predictions, betting analysis, odds interpretation, handicap analysis, over/under, correct score, 比赛预测, 足球分析, 胜平负, 让球盘, 大小球, 比分预测, 盘口, 赔率, 足彩, 竞彩, 下注建议. Launches 8 parallel sub-agents with 3-stage adversarial review to produce concrete probability predictions for 1X2, Asian handicap, Over/Under, and Correct Score.
---

# Football Betting Analysis Skill

## Overview

Reverse-engineer bookmaker pricing logic through 8 parallel analysis dimensions. Find the gap between what odds say and what fundamentals/statistics/history suggest — that gap is where betting value lives.

**Language rule:** All internal reasoning is in English. Output to the user in their language.

**Core principle:** Not predicting results. Finding mispricing.

## When to Use

**Trigger immediately when user mentions ANY of:**
- Match prediction / analysis / evaluation for football/soccer
- Betting / odds / handicap / spread / over-under questions
- Score prediction / result forecast
- 比赛预测 / 分析比赛 / 足球分析 / 比分预测
- 胜平负 / 让球盘 / 大小球 / 盘口 / 赔率
- 足彩 / 竞彩 / 下注 / 投注建议
- "这场比赛怎么看" / "帮我看看这场" / "今晚的比赛"
- Any question involving odds data, bookmaker analysis, or betting value

**Required:** User must provide fixture ID, league ID, and season, OR team names + league name (you look up IDs).

## Architecture

```
User request: "Analyze Brazil vs Germany"
  → Master agent (you): spawn 8 parallel sub-agents
    ├── A: fundamentals.py        (form, H2H, standings from football-data.org)
    ├── B: odds_signals.py        (odds movement from The Odds API)
    ├── C: historical_backtest.py (league baseline from football-data.org)
    ├── D: bookmaker_divergence.py(40+ bookmaker dispersion from The Odds API)
    ├── E: market_sentiment.py    (sharp/retail odds + web search predictions)
    ├── F: objective_factors.py   (web search: injuries, squad, fatigue)
    ├── G: tactical_matchup.py    (web search: lineups/formations + soccerdata stats)
    └── H: player_coach_xg.py     (soccerdata xG + web search coach/player data)
  → Wait for ALL 8 to complete
  → Feed results to aggregator for cross-validation + adversarial review
  → Present final report to user

Data sources:
  football-data.org (10 req/min) → fixtures, standings, H2H, results
  soccerdata (no limits)         → xG, per-game stats, player data
  The Odds API (500 credits/mo)  → odds from 40+ bookmakers
  Web search                     → injuries, lineups, coach, team news
```

## Execution Protocol

### Step 0: Verify API Keys + Dependencies

Three things to check before starting:

**1. FOOTBALL_DATA_KEY** (match data):
```bash
if (-not $env:FOOTBALL_DATA_KEY) { Write-Output "MISSING: FOOTBALL_DATA_KEY" }
```
Register: https://www.football-data.org/client/register (free, 10 req/min)

**2. ODDS_API_KEY** (odds data):
```bash
if (-not $env:ODDS_API_KEY) { Write-Output "MISSING: ODDS_API_KEY" }
```
Register: https://the-odds-api.com/#get-access (free, 500 credits/month)

**3. soccerdata** (xG + detailed stats, optional):
```bash
pip install soccerdata 2>$null; python -c "import soccerdata; print('soccerdata: OK')"
```
If not installed, agents G and H will have reduced capability.

If either API key is missing, **STOP and tell the user exactly which key is missing and where to register it.**

```bash
# Quick verify
python -c "from scripts.api.football_data import get_competitions; c=get_competitions(); print(f'FOOTBALL_DATA_KEY: OK — {len(c)} competitions')"
python -c "from scripts.api.odds_api import get_sports; s=get_sports(); print(f'ODDS_API_KEY: OK — {len(s)} sports')"
```

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
- If any sub-agent returns an error, record it and continue
- Agents F, G, H use **web search** for real-time data. See web search section below.
- Install: `pip install requests soccerdata`

### Web Search: Recommended Sites

When API data is incomplete, use these GFW-accessible, structured-data websites:

| Category | Sites |
|----------|-------|
| Injuries / Team News | sportsmole.co.uk, goal.com/en, besoccer.com |
| Lineups / Formations | flashscore.com, sofascore.com, int.soccerway.com |
| Coach Info | footballcritic.com, soccerbase.com |
| Player Stats | sofascore.com, fotmob.com |
| Predictions / Previews | sportsmole.co.uk, livescore.com |
| Chinese sources | dongqiudi.com (懂球帝), hupu.com (虎扑) |

### Step 3: Run the aggregator

After all 8 sub-agents complete, feed their collected JSON results to the aggregator:

```
Run: python scripts/aggregator.py <subagent_results.json>
```

Or apply the cross-validation logic from `aggregator.py` directly in your reasoning.

### Step 4: Present the final report

**Output language must match the user's language.** The report MUST include:

1. **Predictions** — the most important section. Concrete probability estimates synthesized from all agents:
   - 1X2: Home X% | Draw Y% | Away Z% → Prediction: [outcome] at [probability]% confidence
   - Asian Handicap: line +/-X.X → direction [Home/Away] cover probability Y%
   - Over/Under X.X: Over Y% → direction [Over/Under]
   - List which data sources contributed to each prediction

2. **Market Phase** — how far from kickoff, what phase, what action to take
3. **Summary** — one-line overall assessment
4. **Conflicts & Consensus** — which dimensions disagree (conflicts) and agree (consensus)
5. **Agent findings** — each agent's output with adversarial adjustment (strength→adjusted)
6. **Recommendations** — per bet type: Recommend / Watch / Avoid with reasoning
7. **Data Sufficiency** — which agents are reliable, what to trust/ignore
8. **Adversarial flags** — which agents were downgraded and why

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

Two free API keys required:
```bash
set FOOTBALL_DATA_KEY=your_key_here   # https://www.football-data.org/client/register
set ODDS_API_KEY=your_key_here        # https://the-odds-api.com/#get-access
```
Install deps: `pip install requests soccerdata`

**If rate limit is hit:** Report the error clearly. User can upgrade their plan for more requests.

## Looking Up Competition IDs

football-data.org uses different competition codes. Search with:

```bash
# List available competitions
python -c "from scripts.api.football_data import get_competitions; from scripts.utils import print_json; print_json(get_competitions())"

# Get teams in a competition
python -c "from scripts.api.football_data import get_standings; from scripts.utils import print_json; print_json(get_standings('<competition_id>'))"
```

If you can't find a competition code, web search `"player name" + "recent matches"` to find team/league context.

## Quick Reference: Common Competition IDs

| Competition | football-data.org ID |
|------------|---------------------|
| Premier League | PL |
| Bundesliga | BL1 |
| Serie A | SA |
| La Liga | PD |
| Ligue 1 | FL1 |
| Champions League | CL |
| World Cup | WC |
