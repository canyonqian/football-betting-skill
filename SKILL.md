---
name: football-betting-analysis
description: Use when the user wants to predict, analyze, or evaluate football/soccer matches — including match predictions, betting analysis, odds interpretation, handicap analysis, over/under, correct score, 比赛预测, 足球分析, 胜平负, 让球盘, 大小球, 比分预测, 盘口, 赔率, 足彩, 竞彩, 下注建议. Launches multi-angle analysis with web search to produce predictions for 1X2, Asian handicap, Over/Under, and Correct Score.
---

# Football Betting Analysis Skill

## Overview

Analyse football matches using free public data sources. No API keys required.

**Data sources:**
- 竞彩网 sporttery.cn — all bet types (1X2, AH, correct score, HT/FT, total goals), no key
- Flashscore via Playwright — predicted lineups, formations, player positions, injuries
- Web search — team news, player/coach analysis, form, tactical analysis

**Language rule:** Internal reasoning in English. Output to user in their language.

## Architecture

```
User: "Analyze Brazil vs Morocco"
  Step 1: python scripts/odds_analysis.py "Brazil" "Morocco"
          -> all odds for ALL markets (HAD/HHAD/CRS/HAFU/TTG)
  Step 2: python scripts/flashscore_data.py "Brazil" "Morocco"
          -> lineups, formations, starting XI, injuries
  Step 3: Web search for:
          - Team recent form, FIFA rankings, squad info
          - Key player recent club form, injuries, suspensions
          - Coach tactical style, club vs national team record
          - Upset indicators (form mismatch, tactical counters, injury impact)
  Step 4: python scripts/aggregator.py <odds.json> <flashscore.json>
          -> synthesise all data into predictions
  Step 5: Present final report:
          - 1X2 probabilities + direction
          - Asian Handicap 3-way (让胜/让平/让负) with EV analysis
          - Correct Score top 5 with probabilities
          - Over/Under 2.5 probabilities
          - Half-Time/Full-Time prediction
          - Upset detection and reasoning
          - Recommendations per bet type
```

## Execution Protocol

### Step 1: Get odds (ALL markets)

```bash
python scripts/odds_analysis.py "Brazil" "Morocco" > odds.json
```

Returns ALL 5 markets from 竞彩:
- HAD (胜平负) — 1X2 with fair probabilities
- HHAD (让球盘) — 3-way (让胜/让平/让负) with EV
- CRS (比分) — all 28+ scores ranked by probability
- HAFU (半全场) — 9 HT/FT combos
- TTG (总进球数) — 0-7+ goals distribution, O/U 2.5

### Step 2: Get lineups

```bash
python scripts/flashscore_data.py "Brazil" "Morocco" > lineups.json
```

Returns formations, starting XI (names + positions), injuries.

### Step 3: Web search for context

Search for each team:
- Recent form (last 5-10 matches, results)
- Squad overview (strengths, weaknesses, style)
- Key player club form (this season stats, goals/assists)
- Coach profile (tactical approach, tenure, record)
- Injuries, suspensions, team news

Sites: sportsmole.co.uk, sofascore.com, transfermarkt.com, dongqiudi.com, hupu.com

### Step 4: Aggregate

```bash
python scripts/aggregator.py odds.json lineups.json
```

Produces: 1X2, AH, Correct Score, O/U, HT/FT predictions + upset analysis.

### Step 5: Present report

Must include: predictions per bet type, upset analysis, data quality assessment, recommendations.

## Reading the Markets

### Correct Score Overround
The CRS market has ~28% overround — high but normal for this bet type. The top 5 scores typically cover 55-60% of probability mass. The most likely score is NOT necessarily the most likely outcome — it's the single score the market considers most probable among 28+ options.

### Total Goals / O2.5
The TTG market has ~20% overround. The O2.5 probability is derived by summing P(0)+P(1)+P(2) for Under and P(3+)+ for Over. A 50/50 split = market has no clear direction.

### Asian Handicap 3-Way
竞彩 HHAD is a 3-way bet, not 2-way like Western AH. All three outcomes (让胜/让平/让负) are bettable. The draw (让平) typically has 25-30% probability and is the most commonly overlooked option.

### Upset Detection
Key indicators:
- Deep handicap but low HAD conviction → market may be overconfident
- HT/FT disagrees with HAD → time-of-scoring mismatch
- Injuries not priced in → squad impact underestimated
- Formation mismatch → tactical counter (e.g. 3-5-2 vs 4-3-3)
- Coach record vs opponent → historical edge

## Web Search Prompt for Context

For team/player/coach analysis, search:
```
"{home}" football recent results form 2026
"{away}" football recent results form 2026
"{home}" "{away}" head to head history
"{home}" team news injuries "{match_date}"
"{home}" coach tactics style
"{home_key_player}" club season stats 2025-26
"{away_key_player}" club season stats 2025-26
```

Use results to:
1. Adjust market 1X2 probabilities based on form/fitness
2. Add upset signals based on tactical matchups
3. Contextualise score predictions with team scoring patterns

## Install

```bash
npx skills add canyonqian/football-betting-skill --all -g
pip install requests playwright
playwright install chromium
```
