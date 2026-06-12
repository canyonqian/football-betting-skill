# API-Football v3 Reference

## Base URL
```
https://api-football-v1.p.rapidapi.com/v3
```

## Authentication
Header: `x-rapidapi-key: YOUR_KEY`
Header: `x-rapidapi-host: api-football-v1.p.rapidapi.com`

## Rate Limits (Free Tier)
- 100 requests/day
- Header: `x-ratelimit-requests-limit` / `x-ratelimit-requests-remaining`

## Key Endpoints

### Fixtures
| Endpoint | Params | Returns |
|----------|--------|---------|
| `/fixtures` | league, season, team, status, from, to | Match list |
| `/fixtures?id=X` | id | Single match with events/lineups/stats/players |
| `/fixtures/headtohead` | h2h (`teamA-teamB`) | H2H history |

### Odds
| Endpoint | Params | Returns |
|----------|--------|---------|
| `/odds` | fixture, league, season, bookmaker, bet, page | Pre-match odds (7-day history, 3hr updates) |
| `/odds/live` | fixture, league, bet | Live in-play odds (5-60s updates) |
| `/odds/mapping` | page | Fixture→odds availability (daily) |
| `/odds/bookmakers` | — | All bookmaker IDs |
| `/odds/bets` | — | All bet type IDs |

### Teams & Players
| Endpoint | Params | Returns |
|----------|--------|---------|
| `/teams` | id, league, season, name, country | Team info |
| `/teams/statistics` | team, league, season | Team stats (form, goals, cards) |
| `/players` | team, league, season, search, page | Player info |
| `/players/squads` | team | Current squad |
| `/injuries` | team, league, season, fixture, player | Injuries & suspensions |

### Other
| Endpoint | Params | Returns |
|----------|--------|---------|
| `/standings` | league, season, team | League table |
| `/predictions` | fixture | Win%/goals% predictions |
| `/leagues` | id, team, country, season, search | Competition info |
| `/transfers` | player, team | Transfer records |

## Bet Type IDs
| ID | Name |
|----|------|
| 1 | Match Winner (1X2) |
| 2 | Asian Handicap |
| 5 | Goals Over/Under |
| 6 | Goals Over/Under First Half |
| 8 | Both Teams Score |
| 12 | Double Chance |
| 45 | Correct Score |
| 46 | HT/FT Result |

## Bookmaker IDs
| ID | Name | Type |
|----|------|------|
| 8 | Pinnacle | Sharp |
| 9 | Bet365 | Retail |
| 2 | William Hill | Retail |
| 4 | Bwin | Retail |
| 3 | Betfair | Sharp |
| 15 | Marathonbet | Sharp |
| 24 | 1xBet | Sharp |
| 26 | Unibet | Retail |

## Odds Response Structure
```json
{
  "response": [
    {
      "league": {"id": 1, "name": "World Cup"},
      "fixture": {"id": 12345, "date": "2026-..."},
      "bookmakers": [
        {
          "id": 8,
          "name": "Pinnacle",
          "bets": [
            {
              "id": 1,
              "name": "Match Winner",
              "values": [
                {"value": "Home", "odd": "1.85"},
                {"value": "Draw", "odd": "3.40"},
                {"value": "Away", "odd": "4.20"}
              ]
            }
          ]
        }
      ]
    }
  ]
}
```
