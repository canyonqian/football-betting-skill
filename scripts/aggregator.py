"""Master Aggregator — cross-validates 8 sub-agent outputs.

This script is NOT meant to be run directly as a Python script. It is a
reference implementation showing the logic the AI agent should apply when
aggregating sub-agent results.

When using this skill, the AI agent:
1. Spawns 8 parallel sub-agents (each runs the respective analysis script)
2. Collects all JSON outputs
3. Feeds them to the logic below to produce the final report

The aggregator:
- Only cross-validates — never pulls raw data (avoids confirmation bias)
- Identifies conflicts (dimensions disagree = interesting spots)
- Identifies consensus (dimensions agree = higher confidence)
- Produces final output: recommend / watch / avoid per bet type
"""

import json
import sys
from typing import Any


def load_subagent_results(results_json: str) -> list[dict]:
    """Parse sub-agent results from JSON string or file."""
    if results_json.strip().startswith("{"):
        # Single result
        return [json.loads(results_json)]
    elif results_json.strip().startswith("["):
        return json.loads(results_json)
    else:
        # Assume file path
        with open(results_json.strip()) as f:
            return json.load(f)


def cross_validate(results: list[dict]) -> dict:
    """Cross-validate sub-agent results and produce final report."""
    
    # Separate valid results from errors
    valid = []
    errors = []
    for r in results:
        if "error" in r:
            errors.append(r)
        else:
            valid.append(r)
    
    if not valid:
        return {
            "error": "All sub-agents failed",
            "sub_agent_errors": [e["error"] for e in errors],
        }
    
    # Extract fixture name
    fixture = valid[0].get("fixture", "Unknown")
    
    # Detect conflicts (where dimensions disagree)
    conflicts = detect_conflicts(valid)
    
    # Detect consensus (where dimensions agree)
    consensus = detect_consensus(valid)
    
    # Build bet recommendations
    bets = build_bet_recommendations(valid, conflicts, consensus)
    
    # Build executive summary
    summary = build_summary(valid, conflicts, consensus, bets)
    
    return {
        "fixture": fixture,
        "timestamp": "",  # Filled by caller
        "sub_agent_summary": [
            {
                "agent": r["agent"],
                "finding": r.get("finding", "Error"),
                "strength": r.get("signal_strength", "none"),
                "error": r.get("error"),
            }
            for r in results
        ],
        "conflicts": conflicts,
        "consensus": consensus,
        "bets": bets,
        "summary": summary,
        "warnings": [e.get("error", "") for e in errors],
    }


def detect_conflicts(valid_results: list[dict]) -> list[dict]:
    """Detect areas where sub-agent findings contradict each other."""
    conflicts = []
    
    # Map agents to their signal direction
    signals = {}
    for r in valid_results:
        agent = r["agent"]
        finding = r.get("finding", "").lower()
        metrics = r.get("key_metrics", {})
        notes = r.get("notes", [])
        signals[agent] = {"finding": finding, "metrics": metrics, "notes": notes}
    
    # Conflict 1: Fundamentals vs Market Sentiment
    f = signals.get("fundamentals", {})
    ms = signals.get("market_sentiment", {})
    if f and ms:
        f_gap = f.get("metrics", {}).get("gap")
        ms_heat = ms.get("metrics", {}).get("overheat_level")
        if f_gap is not None and ms_heat:
            # If fundamentals say undervalue but market is overheating on that side
            if abs(f_gap) > 0.05 and ms_heat == "high":
                conflicts.append({
                    "dimensions": ["fundamentals", "market_sentiment"],
                    "conflict": f"Fundamentals gap={f_gap:.3f} vs market overheating={ms_heat}",
                    "interpretation": "Market may be right — fundamentals model could be missing context",
                })
            elif abs(f_gap) > 0.05 and ms_heat == "low":
                conflicts.append({
                    "dimensions": ["fundamentals", "market_sentiment"],
                    "conflict": f"Fundamentals gap={f_gap:.3f} but market is calm",
                    "interpretation": "Potential value opportunity — market hasn't caught on",
                })
    
    # Conflict 2: Odds signals vs Bookmaker divergence
    os_sig = signals.get("odds_signals", {})
    bm_div = signals.get("bookmaker_divergence", {})
    if os_sig and bm_div:
        bm_level = bm_div.get("metrics", {}).get("match_winner_divergence", {}).get("level")
        os_strength = os_sig.get("finding", "")
        if bm_level in ("high",) and "strong" in os_strength:
            conflicts.append({
                "dimensions": ["odds_signals", "bookmaker_divergence"],
                "conflict": "Odds signals suggest strong direction but bookmakers disagree",
                "interpretation": "Low confidence — wait for consensus or reduce stake",
            })
    
    # Conflict 3: Historical backtest vs odds
    hb = signals.get("historical_backtest", {})
    if hb:
        baseline = hb.get("metrics", {}).get("league_baseline", {})
        odds_profile = hb.get("metrics", {}).get("current_odds_profile", {})
        home_odds = odds_profile.get("home_odds")
        if home_odds and baseline:
            market_prob = 1 / home_odds
            hist_prob = baseline.get("home_win_rate", 0)
            if abs(market_prob - hist_prob) > 0.1:
                conflicts.append({
                    "dimensions": ["historical_backtest", "odds_signals"],
                    "conflict": f"Historical home win rate {hist_prob:.1%} vs market implied {market_prob:.1%}",
                    "interpretation": "Market is pricing differently from historical norms",
                })

    # Conflict 4: Tactical advantage vs market odds
    tm = signals.get("tactical_matchup", {})
    if tm and f:
        f_gap = f.get("metrics", {}).get("gap")
        tm_advantages = tm.get("metrics", {}).get("style_clash", {}).get("tactical_advantages", [])
        if tm_advantages and f_gap is not None and f_gap < -0.05:
            conflicts.append({
                "dimensions": ["tactical_matchup", "fundamentals"],
                "conflict": f"Tactical analysis favors {tm.get('finding', '')[:50]} but fundamentals gap is negative ({f_gap:.3f})",
                "interpretation": "Tactical edge may not be priced in — potential value if fundamentals are wrong",
            })

    # Conflict 5: xG signal vs odds over/under
    pc = signals.get("player_coach_xg", {})
    os_sig = signals.get("odds_signals", {})
    if pc and os_sig:
        xg_proxy = pc.get("metrics", {}).get("xg_proxy", {})
        home_gpg = xg_proxy.get("home", {}).get("goals_per_game", 0)
        away_gpg = xg_proxy.get("away", {}).get("goals_per_game", 0)
        ou_line = os_sig.get("metrics", {}).get("over_under", {}).get("line", "2.5")
        try:
            ou_val = float(ou_line)
            combined_gpg = home_gpg + away_gpg
            if combined_gpg > ou_val + 0.5:
                conflicts.append({
                    "dimensions": ["player_coach_xg", "odds_signals"],
                    "conflict": f"Combined GPG ({combined_gpg:.1f}) exceeds O/U line ({ou_line}) — over may be value",
                    "interpretation": "Market O/U line looks low relative to team scoring rates",
                })
            elif combined_gpg < ou_val - 0.5:
                conflicts.append({
                    "dimensions": ["player_coach_xg", "odds_signals"],
                    "conflict": f"Combined GPG ({combined_gpg:.1f}) below O/U line ({ou_line}) — under may be value",
                    "interpretation": "Market O/U line looks high relative to team scoring rates",
                })
        except (ValueError, TypeError):
            pass

    # Conflict 6: Injury impact vs market odds
    of_sig = signals.get("objective_factors", {})
    if pc and of_sig and f:
        home_injuries = of_sig.get("metrics", {}).get("home", {}).get("injuries", 0)
        away_injuries = of_sig.get("metrics", {}).get("away", {}).get("injuries", 0)
        f_gap = f.get("metrics", {}).get("gap")
        if (home_injuries >= 3 or away_injuries >= 3) and f_gap is not None and abs(f_gap) < 0.03:
            conflicts.append({
                "dimensions": ["objective_factors", "fundamentals"],
                "conflict": f"Significant injuries ({home_injuries}+{away_injuries}) but fundamentals gap is small ({f_gap:.3f})",
                "interpretation": "Injury impact may be underestimated by both fundamentals model and market",
            })
    
    return conflicts


def detect_consensus(valid_results: list[dict]) -> list[dict]:
    """Detect areas where sub-agent findings agree."""
    consensus = []
    
    # Count how many agents lean bullish/bearish on the favorite
    lean_bullish = 0
    lean_bearish = 0
    neutral = 0
    
    for r in valid_results:
        finding = r.get("finding", "").lower()
        # Simple heuristic: check for positive/negative language
        positive_words = ["undervalue", "value", "strong home", "favor", "bullish", 
                         "low overround", "sharp market", "tactical edge", "advantage",
                         "overperform", "clinical"]
        negative_words = ["overvalue", "overheat", "trap", "divergence", "unreliable",
                         "high overround", "avoid", "disadvantage", "underperform",
                         "wasteful"]
        
        pos_count = sum(1 for w in positive_words if w in finding)
        neg_count = sum(1 for w in negative_words if w in finding)
        
        if pos_count > neg_count:
            lean_bullish += 1
        elif neg_count > pos_count:
            lean_bearish += 1
        else:
            neutral += 1
    
    if lean_bullish >= 5:
        consensus.append({
            "dimensions": ["all"],
            "agreement": f"Strong bullish consensus ({lean_bullish}/{len(valid_results)} agents favor the favorite)",
        })
    elif lean_bearish >= 5:
        consensus.append({
            "dimensions": ["all"],
            "agreement": f"Strong bearish consensus ({lean_bearish}/{len(valid_results)} agents oppose the favorite)",
        })
    elif lean_bullish + lean_bearish >= 6:
        consensus.append({
            "dimensions": ["all"],
            "agreement": f"Split opinion — no clear consensus ({lean_bullish} bull, {lean_bearish} bear, {neutral} neutral)",
        })
    
    return consensus


def build_bet_recommendations(valid_results: list[dict],
                               conflicts: list[dict],
                               consensus: list[dict]) -> dict:
    """Build final bet type recommendations."""
    bets = {
        "1x2": {"recommendation": "watch", "confidence": "low", "reasoning": ""},
        "asian_handicap": {"recommendation": "watch", "confidence": "low", "reasoning": ""},
        "over_under": {"recommendation": "watch", "confidence": "low", "reasoning": ""},
    }
    
    # Count conflict severity
    has_conflict = len(conflicts) > 0
    high_conflict = any("trap" in c.get("interpretation", "") for c in conflicts)
    
    # Count consensus
    has_consensus = len(consensus) > 0
    strong_consensus = any("Strong" in c.get("agreement", "") for c in consensus)
    
    # Aggregate signal strengths
    strengths = [r.get("signal_strength", "weak") for r in valid_results if "error" not in r]
    strong_count = sum(1 for s in strengths if s == "strong")
    
    # Decision logic
    if has_consensus and strong_consensus and not has_conflict:
        bets["1x2"]["recommendation"] = "recommend"
        bets["1x2"]["confidence"] = "high"
        bets["1x2"]["reasoning"] = "Strong multi-agent consensus with no conflicts"
    elif has_consensus and has_conflict:
        bets["1x2"]["recommendation"] = "watch"
        bets["1x2"]["confidence"] = "medium"
        bets["1x2"]["reasoning"] = "Consensus exists but conflicts present — monitor odds movement"
    elif high_conflict:
        bets["1x2"]["recommendation"] = "avoid"
        bets["1x2"]["confidence"] = "high"
        bets["1x2"]["reasoning"] = "Major conflicts between analysis dimensions — unreliable signals"
    elif strong_count >= 5:
        bets["1x2"]["recommendation"] = "recommend"
        bets["1x2"]["confidence"] = "medium"
        bets["1x2"]["reasoning"] = "Majority of agents show strong signals"
    
    # Asian handicap follows 1X2 logic loosely
    bets["asian_handicap"]["recommendation"] = bets["1x2"]["recommendation"]
    bets["asian_handicap"]["confidence"] = bets["1x2"]["confidence"]
    bets["asian_handicap"]["reasoning"] = "Follows 1X2 analysis; check odds_signals for AH-specific data"
    
    # Over/Under
    ou_agents = [r for r in valid_results if "over" in r.get("finding", "").lower() or "under" in r.get("finding", "").lower()]
    if len(ou_agents) >= 2:
        bets["over_under"]["recommendation"] = "recommend"
        bets["over_under"]["confidence"] = "medium"
        bets["over_under"]["reasoning"] = "Multiple agents agree on O/U direction"
    
    return bets


def build_summary(valid_results: list[dict], conflicts: list[dict],
                   consensus: list[dict], bets: dict) -> str:
    """Build executive summary text."""
    parts = []
    
    # Agent summary
    for r in valid_results:
        strength = r.get("signal_strength", "none")
        parts.append(f"[{r['agent']}] ({strength}) {r.get('finding', 'No finding')}")
    
    # Conflicts
    if conflicts:
        parts.append(f"\n=== CONFLICTS ({len(conflicts)}) ===")
        for c in conflicts:
            parts.append(f"  [{', '.join(c['dimensions'])}] {c['conflict']}")
            parts.append(f"  → {c['interpretation']}")
    
    # Consensus
    if consensus:
        parts.append(f"\n=== CONSENSUS ({len(consensus)}) ===")
        for c in consensus:
            parts.append(f"  [{', '.join(c['dimensions'])}] {c['agreement']}")
    
    # Recommendations
    parts.append("\n=== RECOMMENDATIONS ===")
    for bet_type, info in bets.items():
        rec = info["recommendation"].upper()
        parts.append(f"  {bet_type}: {rec} (confidence: {info['confidence']}) — {info['reasoning']}")
    
    return "\n".join(parts)


def aggregate(results_list: list[dict]) -> dict:
    """Main entry point: accept list of sub-agent results, return final report."""
    from utils import now_iso
    report = cross_validate(results_list)
    report["timestamp"] = now_iso()
    return report


# --- CLI entry point: accepts JSON file of sub-agent results ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: aggregator.py <subagent_results.json>")
        print("  subagent_results.json: JSON array of sub-agent output objects")
        sys.exit(1)
    
    results = load_subagent_results(sys.argv[1])
    report = aggregate(results)
    
    # Print summary to stdout
    print(report.get("summary", json.dumps(report, indent=2, ensure_ascii=False)))
    print("\n--- FULL REPORT ---")
    print(json.dumps(report, indent=2, ensure_ascii=False))
