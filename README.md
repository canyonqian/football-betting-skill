# Football Betting Analysis Skill

An AI agent skill for football betting analysis. Launches 8 parallel sub-agents + 3-stage adversarial review to produce concrete probability predictions for 1X2, Asian handicap, Over/Under, and Correct Score.

## How It Works

```
User: "Analyze Brazil vs Germany"
  └─ 8 parallel sub-agents ─┐
     A: Fundamentals         │
     B: Odds signals         │
     C: Historical backtest  │── adversarial review ──→ probabilities
     D: Bookmaker divergence │
     E: Market sentiment     │
     F: Objective factors    │
     G: Tactical matchup     │
     H: Player/coach + xG    │
  ───────────────────────────┘

Output:
  1X2: Home 48% | Draw 26% | Away 26%
  AH: -0.5 → Home cover 55%
  O/U: Over 2.5 → 58%
  Scores: 1-0 (16%), 2-0 (13%), 1-1 (12%) ...
```

## Install

```bash
npx skills add canyonqian/football-betting-skill --all -g
pip install requests soccerdata
```

## API Keys

| Key | Register At | Free Tier | Data |
|-----|------------|-----------|------|
| `FOOTBALL_DATA_KEY` | [football-data.org](https://www.football-data.org/client/register) | 10 req/min | Fixtures, results, standings, H2H |
| `ODDS_API_KEY` | [the-odds-api.com](https://the-odds-api.com/#get-access) | 500 credits/mo | 40+ bookmaker odds |

```bash
set FOOTBALL_DATA_KEY=your_key
set ODDS_API_KEY=your_key
```

No credit card required for either. `soccerdata` provides xG and per-game stats via web scraping (no API key needed).

## Data Sources

| Source | Rate Limit | Provides |
|--------|-----------|----------|
| **football-data.org** | 10 req/min | Fixtures, standings, H2H, results |
| **The Odds API** | 500 credits/mo | 1X2, spreads, totals from 40+ bookmakers |
| **soccerdata** | Unlimited | xG (Understat), per-game stats (FBref) |
| **Web search** | Unlimited | Injuries, lineups, coach news (Flashscore, Sofascore, Sports Mole) |

## Requirements

| Dependency | Required | Purpose |
|-----------|----------|---------|
| Python 3.9+ | Yes | Runtime |
| `requests` | Yes | HTTP client |
| `soccerdata` | Recommended | Real xG and per-game stats |
| `FOOTBALL_DATA_KEY` | Yes | Free from football-data.org |
| `ODDS_API_KEY` | Yes | Free from the-odds-api.com |

## Troubleshooting

If the skill doesn't appear after `npx skills add`, copy manually to your agent's skills directory and restart:

| Agent | Directory |
|-------|-----------|
| OpenCode | `~\.config\opencode\skills\football-betting-analysis\` |
| Claude Code | `~\.claude\skills\football-betting-analysis\` |
| Cursor | `~\.cursor\skills\football-betting-analysis\` |
