import requests, os
key = os.environ["FOOTBALL_API_KEY"]
r = requests.get("https://v3.football.api-sports.io/teams/statistics", 
                  params={"team": 33, "league": 39, "season": 2024},
                  headers={"x-apisports-key": key})
print(f"Status: {r.status_code}")
print(f"Headers: {dict(r.headers)}")
for h in sorted(r.headers):
    if "rate" in h.lower() or "limit" in h.lower() or "remaining" in h.lower():
        print(f"  {h}: {r.headers[h]}")
