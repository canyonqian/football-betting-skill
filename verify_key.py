import requests, json, os
key = os.environ["FOOTBALL_API_KEY"]
r = requests.get("https://v3.football.api-sports.io/status", headers={"x-apisports-key": key})
print(f"Status: {r.status_code}")
print(json.dumps(r.json(), indent=2)[:500])
