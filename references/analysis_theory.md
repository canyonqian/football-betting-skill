# Football Betting Analysis Theory

## 1. Kelly Criterion — Optimal Stake Sizing

```
f* = (bp - q) / b

Where:
  f* = fraction of bankroll to bet
  b  = decimal odds - 1
  p  = your estimated win probability
  q  = 1 - p

Example: odds 2.00, you think 55% win chance
  f* = (1 × 0.55 - 0.45) / 1 = 0.10 → bet 10% of bankroll

Practical: Use fractional Kelly (1/4 or 1/2) for safety.
```

## 2. Overround (Vig) — Bookmaker's Margin

```
Overround = Σ(1/odds_i) - 1

Example: 1X2 odds 1.85 / 3.40 / 4.20
  Overround = 1/1.85 + 1/3.40 + 1/4.20 - 1
            = 0.5405 + 0.2941 + 0.2381 - 1
            = 0.0727 (7.27%)

Interpretation:
  < 3%  → Very sharp market (Pinnacle on major leagues)
  3-6%  → Normal market
  6-10% → Wider margin (smaller leagues, exotic bets)
  >10%  → High margin — less value to find
```

## 3. Asian Handicap Mechanics

| Handicap | Meaning |
|----------|---------|
| 0 | Draw no bet |
| -0.25 | Favorite loses 1/4 stake on draw |
| -0.5 | Favorite must win (half-ball) |
| -0.75 | Favorite wins by 1 = half win; by 2+ = full win |
| -1 | Favorite must win by 2+ for full win; by 1 = push |
| -1.25 | Favorite wins by 1 = half loss; by 2+ = full win |
| -1.5 | Favorite must win by 2+ |

**Water level (水位)**: The odds on each side. 
- Low water (< 1.80): Bookmaker confident, low payout
- High water (> 2.00): Bookmaker less confident, attractive payout

**Key pattern**: When the handicap line moves but the water level stays flat 
→ genuine line movement (bookmaker really changed their view).
When water level moves but line stays → market pressure, not bookmaker conviction.

## 4. Odds Movement Patterns

### Pattern A: Early Stability → Late Sharp Move
```
Opening (3 days before): 1.90 / 3.40 / 4.00
Middle (1 day before):   1.88 / 3.50 / 4.10
Closing (1 hour before): 1.72 / 3.80 / 4.80  ← SHARP MOVE

Interpretation: Strong late money on home team. 
High signal — likely smart money.
```

### Pattern B: Steady Drift
```
Opening: 2.10 / 3.30 / 3.50
Daily:   2.08 → 2.05 → 2.02 → 1.98

Interpretation: Gradual money flow. 
Moderate signal — market slowly adjusting, no urgency.
```

### Pattern C: Spike and Revert
```
Opening:  1.95
Spike to: 1.75 (brief)
Revert:   1.90

Interpretation: Large single bet moved line, then corrected. 
Low signal — one punter, not information.
```

### Pattern D: Odds lengthening on favorite
```
Favorite opens at 1.60, drifts to 1.75

Interpretation: Money flowing AGAINST favorite.
Very negative signal — smart money opposing the favorite.
```

## 5. Contrarian Indicators

**When the public is heavily on one side but odds move opposite:**
→ Follow the odds movement. The bookmaker is absorbing the public money 
  and NOT adjusting — they're confident.

**When sharp odds differ from retail odds by > 0.10:**
→ Pinnacle/Betfair > 2.00 on a side while Bet365 < 1.90
→ Follow the sharp bookmaker. Retail is shading for public bias.

**When xG contradicts actual results over 5+ matches:**
→ A team scoring more than xG suggests is running hot → fade them
→ A team scoring less than xG suggests is due for regression → back them

## 6. League-Specific Traits

| League | Home Win% | Avg Goals | Over 2.5% | Style |
|--------|-----------|-----------|-----------|-------|
| Premier League | ~45% | 2.8 | 55% | Physical, moderate scoring |
| La Liga | ~48% | 2.5 | 45% | Technical, lower scoring |
| Bundesliga | ~45% | 3.1 | 60% | Open, high scoring |
| Serie A | ~42% | 2.7 | 50% | Tactical, moderate |
| Ligue 1 | ~43% | 2.6 | 48% | Defensive |
| World Cup | ~43% | 2.4 | 42% | Cautious, low scoring |
| Euros | ~44% | 2.3 | 40% | Cautious |
| Champions League | ~48% | 2.9 | 53% | Quality attack |

## 7. Value Detection Framework

A bet has value when:
```
Your_Estimated_Probability > 1 / Decimal_Odds
```

Example: You think team A has 60% win chance. Odds = 2.00 (50% implied).
  60% > 50% → VALUE BET

Example: You think team A has 40% win chance. Odds = 1.80 (55.6% implied).
  40% < 55.6% → NO VALUE

The gap between your estimate and the market's estimate is your edge.
If your estimate is not demonstrably better than the market's, you have no edge.
