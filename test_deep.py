"""Deep test of actual endpoint responses."""
import os, json, requests

FK = os.environ.get("FOOTBALL_API_KEY", "")
OK = os.environ.get("ODDS_API_KEY", "")
H = {"x-apisports-key": FK}

def aget(url, params=None):
    r = requests.get(url, headers=H, params=params or {})
    return r.status_code, r.json()

# Find EPL 2024-2025 fixture
print("=== Find EPL fixture ===")
s, d = aget("https://v3.football.api-sports.io/fixtures", {"league": 39, "season": 2024, "from": "2024-08-10", "to": "2024-08-20"})
print(f"Status: {s}, Results: {d.get('results', 0)}")
if not d.get("response"):
    s, d = aget("https://v3.football.api-sports.io/fixtures", {"league": 39, "season": 2023, "status": "FT"})
    print(f"EPL 2023: {d.get('results', 0)}")
    if not d.get("response"):
        print("NO EPL FIXTURES — trying WC 2022")
        s, d = aget("https://v3.football.api-sports.io/fixtures", {"league": 1, "season": 2022, "status": "FT"})
        print(f"WC 2022: {d.get('results', 0)}")

if d.get("response"):
    fixture = d["response"][0]
    fid = fixture["fixture"]["id"]
    home = fixture["teams"]["home"]["name"]
    away = fixture["teams"]["away"]["name"]
    home_id = fixture["teams"]["home"]["id"]
    away_id = fixture["teams"]["away"]["id"]
    date = fixture["fixture"]["date"]
    league_id = fixture["league"]["id"]
    season = fixture["league"]["season"]
    print(f"Fixture: {fid} | {home} vs {away} | {date} | League {league_id} S{season}")

    # Team stats
    print("\n=== Team Stats ===")
    s, d2 = aget("https://v3.football.api-sports.io/teams/statistics", {"team": home_id, "league": league_id, "season": season})
    resp = d2.get("response", {})
    if resp:
        print(f"Form: {resp.get('form', 'N/A')}")
        print(f"Fixtures.played keys: {list(resp.get('fixtures', {}).get('played', {}).keys())}")
        gl = resp.get("goals", {}).get("for", {})
        print(f"Goals.for keys: {list(gl.keys())}")
        total_f = gl.get("total", {})
        print(f"  home goals: {total_f.get('home', 0)}")
        lu = resp.get("lineups", [])
        if lu:
            print(f"  Lineups: {lu[0]}")
        mn = resp.get("goals", {}).get("for", {}).get("minute", {})
        if mn:
            print(f"  Goal minute keys: {list(mn.keys())[:3]}")
            for k, v in list(mn.items())[:2]:
                print(f"    {k}: {v}")

    # Predictions
    print(f"\n=== Predictions ===")
    s, d3 = aget("https://v3.football.api-sports.io/predictions", {"fixture": fid})
    print(f"Status: {s}")
    if d3.get("response"):
        pred = d3["response"][0]
        p = pred.get("predictions", {})
        print(f"  winner: {p.get('winner', {})}")
        print(f"  percent: {p.get('percent', {})}")
        print(f"  advice: {p.get('advice', 'N/A')}")

    # Coach
    print(f"\n=== Coach ===")
    s, d4 = aget("https://v3.football.api-sports.io/coachs", {"team": home_id})
    print(f"Status: {s}, Results: {d4.get('results', 0)}")
    if d4.get("response"):
        c = d4["response"][0]
        print(f"  Name: {c.get('name')}, Teams: {len(c.get('career', []))}")

    # Injuries
    print(f"\n=== Injuries ===")
    s, d5 = aget("https://v3.football.api-sports.io/injuries", {"team": home_id, "league": league_id, "season": season})
    print(f"Status: {s}, Results: {d5.get('results', 0)}")
    if d5.get("response"):
        inj = d5["response"][0]
        print(f"  Player: {inj.get('player', {}).get('name')}, Type: {inj.get('player', {}).get('type')}")

    # Players squad
    print(f"\n=== Players Squad ===")
    s, d6 = aget("https://v3.football.api-sports.io/players/squads", {"team": home_id})
    print(f"Status: {s}, Results: {d6.get('results', 0)}")
    if d6.get("response"):
        squad = d6["response"][0]
        players = squad.get("players", [])
        print(f"  Squad size: {len(players)}")
        if players:
            print(f"  First player: {players[0].get('name')} ({players[0].get('position')})")

# The Odds API
print("\n=== The Odds API ===")
r = requests.get("https://api.the-odds-api.com/v4/sports/soccer_epl/odds",
                  params={"apiKey": OK, "regions": "eu", "markets": "h2h,spreads,totals", "oddsFormat": "decimal"})
print(f"Status: {r.status_code}, Remaining: {r.headers.get('x-requests-remaining', '?')}")
od = r.json()
if od and len(od) > 0:
    m = od[0]
    print(f"Match: {m.get('home_team')} vs {m.get('away_team')}")
    print(f"Keys: {list(m.keys())}")
    for bm in m.get("bookmakers", [])[:2]:
        print(f"  BM: {bm.get('title')}, Markets: {[mk['key'] for mk in bm.get('markets', [])]}")
        for mk in bm.get("markets", []):
            outcomes = mk.get("outcomes", [])
            if mk["key"] == "h2h":
                print(f"    h2h: {[{o['name']: o['price']} for o in outcomes]}")
            elif mk["key"] == "totals":
                print(f"    totals: {[{o['name']: {'price': o['price'], 'point': o.get('point')}} for o in outcomes[:2]]}")
else:
    print("No odds data returned")
