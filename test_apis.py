"""Quick API test for both endpoints."""
import os
import json
import requests

# Test API-Football
print("=== API-Football v3 ===")
key = os.environ.get("FOOTBALL_API_KEY", "")
print(f"Key present: {bool(key)}")

r = requests.get("https://v3.football.api-sports.io/status", headers={"x-apisports-key": key})
print(f"Status test: {r.status_code}")
print(json.dumps(r.json(), indent=2)[:500])

# Test a real endpoint
r2 = requests.get("https://v3.football.api-sports.io/leagues", headers={"x-apisports-key": key}, params={"search": "World Cup"})
print(f"\nLeagues search: {r2.status_code}")
data = r2.json()
print(f"Response keys: {list(data.keys())}")
if data.get("response"):
    print(f"Results: {len(data['response'])}")
    print(json.dumps(data["response"][0], indent=2)[:300])

print("\n=== The Odds API ===")
key2 = os.environ.get("ODDS_API_KEY", "")
print(f"Key present: {bool(key2)}")
r3 = requests.get("https://api.the-odds-api.com/v4/sports", params={"apiKey": key2})
print(f"Status: {r3.status_code}")
print(f"Remaining: {r3.headers.get('x-requests-remaining', '?')}")
data3 = r3.json()
soccer_sports = [s for s in data3 if "soccer" in s.get("key", "")]
print(f"Soccer sports: {len(soccer_sports)}")
for s in soccer_sports[:5]:
    print(f"  {s['key']}: {s['title']}")
