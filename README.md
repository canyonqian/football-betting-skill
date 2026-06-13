# Football Betting Analysis Skill

AI agent skill for football betting analysis. Uses free public data — no API keys needed.

## How It Works

```
User: "Analyze Brazil vs Morocco"
  Step 1: 竞彩.cn 完整数据 -> odds_analysis.py
          ALL markets: 1X2, 让球盘, 比分(28+), 半全场, 总进球
  Step 2: Flashscore              -> flashscore_data.py
          阵容, 阵型, 首发11人, 伤病
  Step 3: Web search              -> AI agent
          球队状态, 球员俱乐部表现, 教练战术
  Step 4: Aggregator              -> aggregator.py
          1X2预测 + 让球盘3选1 + 比分预测 + 大小球 + 冷门检测
```

## Data Sources (all free, unlimited)

| Source | Provides |
|--------|----------|
| 竞彩网 sporttery.cn | 5 markets: 胜平负, 让球(3选1), 比分, 半全场, 总进球 |
| Flashscore + Playwright | 阵容, 阵型, 首发名单, 位置, 伤病 |
| Web search | 球队状态, 球员数据, 教练分析 |

## Install

```bash
npx skills add canyonqian/football-betting-skill --all -g
pip install requests playwright
playwright install chromium
```

## Usage

```bash
# Get all odds
python scripts/odds_analysis.py "Brazil" "Morocco"

# Get lineups
python scripts/flashscore_data.py "Brazil" "Morocco"

# Synthesise
python scripts/aggregator.py odds.json lineups.json
```
