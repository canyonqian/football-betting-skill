# Football Betting Analysis Skill

An AI agent skill for football betting analysis. Launches 8 parallel sub-agents + 3-stage adversarial review to reverse-engineer bookmaker pricing logic and produce concrete probability predictions for 1X2, Asian handicap, Over/Under, and Correct Score markets.

## How It Works

```
User: "Analyze Brazil vs Germany"
  └─ 8 parallel sub-agents ─┐
     A: Fundamentals         │
     B: Odds signals         │
     C: Historical backtest  │── cross-validate ──→ adversarial review ──→ probabilities
     D: Bookmaker divergence │
     E: Market sentiment     │
     F: Objective factors    │
     G: Tactical matchup     │
     H: Player/coach + xG    │
  ───────────────────────────┘

Output:
  1X2: Home 48% | Draw 26% | Away 26%
  AH: line -0.5 → Home cover 55%
  O/U: Over 2.5 → 58%
  Scores: 1-0 (16%), 2-0 (13%), 1-1 (12%) ...
```

## Install

```bash
npx skills add canyonqian/football-betting-skill --all -g
pip install requests
pip install soccerdata    # optional, for real xG data
```

### If the skill doesn't appear after install

Each agent has its own skills directory. If `npx skills add` doesn't make the skill appear, copy manually:

| Agent | Command |
|-------|---------|
| OpenCode | `xcopy /E %USERPROFILE%\.agents\skills\football-betting-analysis %USERPROFILE%\.config\opencode\skills\football-betting-analysis\` |
| Claude Code | `xcopy /E %USERPROFILE%\.agents\skills\football-betting-analysis %USERPROFILE%\.claude\skills\football-betting-analysis\` |
| Cursor | `xcopy /E %USERPROFILE%\.agents\skills\football-betting-analysis %USERPROFILE%\.cursor\skills\football-betting-analysis\` |

**Restart the agent after copying** — skills are loaded at startup.

## API Keys

**Two free API keys are required:**

| Key | Register At | Free Tier | Used For |
|-----|------------|-----------|----------|
| `FOOTBALL_API_KEY` | [dashboard.api-football.com](https://dashboard.api-football.com/register) | 100 req/day | Teams, players, fixtures, statistics, injuries, lineups |
| `ODDS_API_KEY` | [the-odds-api.com](https://the-odds-api.com/#get-access) | 500 credits/month | 1X2, spreads, totals from 40+ bookmakers |

```bash
set FOOTBALL_API_KEY=your_football_key
set ODDS_API_KEY=your_odds_key
```

Both free tiers require no credit card.

## Usage

Once installed, the skill loads automatically when you ask your AI agent to analyze a match:

```
Analyze Brazil vs Germany in the World Cup
Analyze fixture_id=12345, league_id=1, season=2026
Look at the odds for tonight's Premier League game
```

If you don't have fixture IDs, the skill will look them up for you using team names and league.

## Requirements

| Dependency | Required | Purpose |
|-----------|----------|---------|
| Python 3.9+ | Yes | Script runtime |
| `requests` | Yes | HTTP client for both APIs |
| `soccerdata` | Optional | Real xG data from Understat (agent H) |
| `FOOTBALL_API_KEY` | Yes | Free from [dashboard.api-football.com](https://dashboard.api-football.com/register) |
| `ODDS_API_KEY` | Yes | Free from [the-odds-api.com](https://the-odds-api.com/#get-access) |

## Data Sources

| Data | Source | Free Tier |
|------|--------|-----------|
| Teams, players, fixtures, stats, injuries | [API-Football v3](https://www.api-football.com/) | 100 req/day |
| Odds (1X2, spreads, totals), 40+ bookmakers | [The Odds API](https://the-odds-api.com/) | 500 credits/month |

## Output

The skill produces a structured report per match:

- **Summary** — one-line assessment
- **Conflicts & Consensus** — where dimensions disagree (most interesting) and agree (most reliable)
- **Agent findings** — each of the 8 sub-agents' key output
- **Betting recommendations** — Recommend / Watch / Avoid per bet type with reasoning
- **Risk warnings** — key factors affecting confidence
