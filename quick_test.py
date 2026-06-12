import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
os.environ["FOOTBALL_DATA_KEY"] = "6d938bd5d794461ea865a576c5ba22ae"
os.environ["ODDS_API_KEY"] = "ae614b1ff0b16554d073cebfbb4f6a1e"

from scripts.api.football_data import get_matches, get_match
from scripts.api.odds_api import get_sport_key, get_odds

# Find matches
m = get_matches("PL")
print(f"Premier League matches: {len(m)}")
for x in m[:5]:
    print(f"  {x['id']}: {x['homeTeam']['name']} vs {x['awayTeam']['name']} ({x['status']})")

# Test sport key
sk = get_sport_key("PL")
print(f"\nSport key for PL: {sk}")

if sk:
    od = get_odds(sk)
    print(f"Odds matches: {len(od)}")
    if od:
        print(f"  First: {od[0]['home_team']} vs {od[0]['away_team']}")
