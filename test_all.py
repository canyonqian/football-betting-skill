"""Test all 8 sub-agents with football-data.org + Odds API."""
import subprocess, json, sys, os

os.environ["FOOTBALL_DATA_KEY"] = "6d938bd5d794461ea865a576c5ba22ae"
os.environ["ODDS_API_KEY"] = "ae614b1ff0b16554d073cebfbb4f6a1e"

HOME = r"C:\Users\11230\Desktop\football-skill\scripts\analysis"

agents = [
    ("fundamentals.py", "537785", "PL", "2024"),
    ("odds_signals.py", "537785", "PL", "2024"),
    ("historical_backtest.py", "537785", "PL", "2024"),
    ("bookmaker_divergence.py", "537785", "PL", "2024"),
    ("market_sentiment.py", "537785", "PL", "2024"),
    ("objective_factors.py", "537785", "PL", "2024"),
    ("tactical_matchup.py", "537785", "PL", "2024"),
    ("player_coach_xg.py", "537785", "PL", "2024"),
]

results = []
for name, mid, cid, season in agents:
    cmd = ["python", name, mid, cid, season]
    print(f"\n--- {name} ---")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90, cwd=HOME)
        if r.returncode != 0:
            print(f"  FAIL (exit={r.returncode})")
            err = r.stderr.strip().split("\n")[-3:]
            for e in err:
                print(f"  stderr: {e[:150]}")
            results.append((name, "FAIL", err[-1][:80] if err else ""))
        else:
            try:
                data = json.loads(r.stdout)
                agent = data.get("agent", "?")
                finding = data.get("finding", "")[:80]
                strength = data.get("signal_strength", "?")
                err = data.get("error", "")
                if err:
                    print(f"  DATA_ERROR: {err[:120]}")
                    results.append((name, "DATA_ERR", err[:80]))
                else:
                    print(f"  OK | {agent} | strength={strength}")
                    print(f"  {finding}")
                    results.append((name, "OK", strength))
            except json.JSONDecodeError:
                print(f"  BAD_JSON: {r.stdout[:200]}")
                results.append((name, "BAD_JSON", ""))
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT")
        results.append((name, "TIMEOUT", ""))

print("\n=== SUMMARY ===")
ok = sum(1 for _, s, _ in results if s == "OK")
for name, status, detail in results:
    marker = "✅" if status == "OK" else "❌"
    print(f"  {marker} {status:8s} {name:25s} {detail}")
print(f"\nPass: {ok}/{len(agents)}")
