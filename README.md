# Football Betting Analysis Skill

An AI agent skill for football betting analysis. Launches 8 parallel sub-agents to reverse-engineer bookmaker pricing logic and identify value opportunities across 1X2, Asian handicap, and Over/Under markets.

## How It Works

```
User: "Analyze Brazil vs Germany"
  └─ 8 parallel sub-agents ─┐
     A: Form vs odds gap    │
     B: Odds signals        │
     C: Historical backtest │
     D: Bookmaker divergence│── cross-validate ──→ Recommend / Watch / Avoid
     E: Market sentiment    │
     F: Objective factors   │
     G: Tactical matchup    │
     H: Player/coach + xG   │
  ──────────────────────────┘
```

Each sub-agent is information-isolated. Conflicts between dimensions are the most valuable signals — where the odds say one thing but fundamentals/tactics/history say another is where edge lives.

## Install

```bash
# Install skill
npx skills add canyonqian/football-betting-skill --all -g

# Install dependencies
pip install requests
pip install soccerdata    # optional, for real xG data

# Configure API key
# Get a free key at https://dashboard.api-football.com/register
set FOOTBALL_API_KEY=your_key_here
```

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
| `requests` | Yes | API-Football v3 HTTP client |
| `soccerdata` | Optional | Real xG data from Understat (agent H) |
| FOOTBALL_API_KEY | Yes | Free from [dashboard.api-football.com](https://dashboard.api-football.com/register) |

## Data Source

All data comes from [API-Football v3](https://www.api-football.com/) via api-sports.io. Free tier: 100 requests/day. No fallback, no workaround — if rate-limited, you need to upgrade.

## Output

The skill produces a structured report per match:

- **Summary** — one-line assessment
- **Conflicts & Consensus** — where dimensions disagree (most interesting) and agree (most reliable)
- **Agent findings** — each of the 8 sub-agents' key output
- **Betting recommendations** — Recommend / Watch / Avoid per bet type with reasoning
- **Risk warnings** — key factors affecting confidence
