# Football Betting Analysis Skill — Design Spec

## 1. Overview

A skill for personal football betting analysis. The core philosophy: **not predicting match results, but reverse-engineering bookmaker pricing logic** — finding the gap between what the odds say and what fundamentals suggest, because that gap is where value lives.

## 2. Scope & Constraints

| Item | Decision |
|------|----------|
| Bet types covered | 1X2 (win/draw/lose), Asian handicap, Over/Under |
| Bet types NOT covered | Correct score, HT/FT (insufficient data for reliable analysis) |
| Data source | API-Football v3 (RapidAPI) — 单一数据源，不设备用 |
| API 额满处理 | 直接报错，不降级、不换源。需要更多额度自行充值升级 |
| Script language | Python 3 |

## 3. Architecture

```
football-skill/
├── SKILL.md                       # Main skill — orchestrates sub-agents
├── scripts/
│   ├── api/
│   │   └── api_football.py        # API-Football v3 wrapper (唯一数据源)
│   ├── analysis/
│   │   ├── fundamentals.py        # A: fundamentals vs odds gap
│   │   ├── odds_signals.py        # B: odds movement signals
│   │   ├── historical_backtest.py # C: historical pattern backtest
│   │   ├── bookmaker_divergence.py# D: multi-bookmaker divergence
│   │   ├── market_sentiment.py    # E: market sentiment
│   │   └── objective_factors.py   # F: player/team depth factors
│   ├── aggregator.py              # Master: cross-validation & summary
│   └── utils.py
└── references/
    ├── api_reference.md
    └── analysis_theory.md
```

## 4. The 6-Agent Pipeline

For each match, SKILL.md instructs the agent to spawn **6 parallel sub-agents**, each responsible for one dimension. Sub-agents are information-isolated — they do not see each other's output.

### A. Fundamentals vs Odds Gap
- **Mission**: Calculate what the odds "should" be based on form, and compare to what the market is actually offering.
- **Inputs**: recent form (last 5-10 matches), home/away split, H2H history, league standings
- **Output**: gap score (how much the market deviates from fundamentals-based expectation)

### B. Odds Movement Signals
- **Mission**: Interpret opening → current odds movement as bookmaker intent.
- **Key signals**: water level changes, line movement (upgrade/downgrade), return rate shifts
- **Output**: direction signal (luring bets vs genuine hedging), confidence level

### C. Historical Odds Pattern Backtest
- **Mission**: For the current odds combination, look up actual match outcomes from past seasons via API-Football v3.
- **Output**: statistical probability vs implied probability deviation, win/loss distribution

### D. Multi-Bookmaker Divergence
- **Mission**: Compare odds across Pinnacle, Bet365, William Hill, etc. to detect divergence.
- **Key metric**: odds dispersion, outlier detection, each bookmaker's historical accuracy
- **Output**: divergence ranking, which bookmaker is historically most accurate for this league

### E. Market Sentiment
- **Mission**: Detect market overheating — betting volume distribution, popular directions, capital flow.
- **Key signals**: heavy money on one side, public bias, contrarian indicators
- **Output**: overheat warning level, contrarian recommendation

### F. Objective Factors
- **Mission**: Identify match-changing variables beyond form and odds.
- **Key factors**: injuries/suspensions of key players, recent lineup changes, squad depth, fatigue
- **Output**: key variables ranked by impact weight, factor that the market may be mispricing

## 5. Aggregator (Master Agent)

The master agent:
1. **Only cross-validates** — never pulls raw data itself (avoids confirmation bias)
2. Receives 6 structured JSON outputs from sub-agents
3. Identifies **conflicts** (where dimensions disagree — these are the interesting spots)
4. Identifies **consensus** (where dimensions agree)
5. Produces final output per bet type: **recommend / watch / avoid**

## 6. Sub-Agent Output Contract

Every sub-agent returns this structure:
```json
{
  "agent": "fundamentals",
  "fixture": "Brazil vs Germany",
  "finding": "Market undervalues Brazil by 0.25 goals",
  "signal_strength": "medium",
  "key_metrics": {
    "expected_handicap": -0.75,
    "actual_handicap": -0.5,
    "gap": 0.25
  },
  "notes": ["Brazil missing starting LB but market hasn't adjusted"]
}
```

## 7. Master Output Contract

```json
{
  "fixture": "Brazil vs Germany",
  "timestamp": "2026-06-15T20:00:00Z",
  "discrepancies": [
    {
      "dimensions": ["fundamentals", "odds_signals"],
      "conflict": "Fundamentals suggest draw, but odds movement is strongly favoring Brazil",
      "interpretation": "Possible trap — odds may be luring bets on Brazil"
    }
  ],
  "consensus": [
    {
      "dimensions": ["historical_backtest", "bookmaker_divergence"],
      "agreement": "Both suggest under 2.5 goals is slightly undervalued"
    }
  ],
  "bets": {
    "1x2": { "recommendation": "avoid", "reasoning": "Conflicting signals" },
    "asian_handicap": { "recommendation": "watch", "reasoning": "Line may move, monitor" },
    "over_under": { "recommendation": "under 2.5", "confidence": "medium" }
  }
}
```

## 8. Analysis Theory Reference

The skill includes an `analysis_theory.md` covering:

| Topic | Content |
|-------|---------|
| Kelly Criterion | Optimal stake sizing formula |
| Overround/Vig | How bookmakers build their margin |
| Asian Handicap mechanics | Water level, half-ball, quarter-ball interpretation |
| Odds movement patterns | Common patterns: early stability → late shift, steady drift, sharp move |
| Contrarian indicators | When to bet against the public |
| League-specific traits | How different leagues have different odds profiles |

## 9. What This Skill Does NOT Do

- Does NOT guarantee winning bets
- Does NOT automate betting execution
- Does NOT provide real-time in-play analysis
- Does NOT cover niche bet types (correct score, HT/FT, cards, corners)
- Does NOT replace personal judgment — it's a decision support tool
