"""Test all 8 sub-agents end-to-end."""
import subprocess, json, sys, os

os.environ["FOOTBALL_API_KEY"] = "5be3b022eb9360a12769eaec2f66a783"
os.environ["ODDS_API_KEY"] = "ae614b1ff0b16554d073cebfbb4f6a1e"

HOME = r"C:\Users\11230\Desktop\football-skill\scripts\analysis"

agents = [
    "fundamentals.py",
    "odds_signals.py", 
    "historical_backtest.py",
    "bookmaker_divergence.py",
    "market_sentiment.py",
    "objective_factors.py",
    "tactical_matchup.py",
    "player_coach_xg.py",
]

FID = "1208021"
LID = "39"
SEASON = "2024"

results = []
for name in agents:
    path = os.path.join(HOME, name)
    print(f"\n=== {name} ===")
    try:
        r = subprocess.run(
            ["python", path, FID, LID, SEASON],
            capture_output=True, text=True, timeout=60,
            cwd=HOME
        )
        if r.returncode != 0:
            print(f"  FAIL (code {r.returncode})")
            print(f"  stderr: {r.stderr[:300]}")
            results.append({"agent": name, "status": "FAIL", "error": r.stderr[:200]})
        else:
            try:
                data = json.loads(r.stdout)
                agent = data.get("agent", "?")
                finding = data.get("finding", "")[:80]
                strength = data.get("signal_strength", "?")
                err = data.get("error", "")
                print(f"  OK | agent={agent} | strength={strength}")
                print(f"  finding: {finding}")
                if err:
                    print(f"  (error in response: {err[:100]})")
                    results.append({"agent": name, "status": "DATA_ERROR", "error": err[:100]})
                else:
                    results.append({"agent": name, "status": "OK", "strength": strength})
            except json.JSONDecodeError:
                print(f"  BAD JSON: {r.stdout[:200]}")
                results.append({"agent": name, "status": "BAD_JSON"})
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT")
        results.append({"agent": name, "status": "TIMEOUT"})
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        results.append({"agent": name, "status": "EXCEPTION", "error": str(e)[:100]})

print("\n=== SUMMARY ===")
ok = sum(1 for r in results if r["status"] == "OK")
fail = sum(1 for r in results if r["status"] != "OK")
print(f"Pass: {ok}/{len(agents)}, Fail: {fail}/{len(agents)}")
for r in results:
    status = r["status"]
    err = r.get("error", "")[:60]
    print(f"  [{status:10s}] {r['agent']:25s} {err}")
