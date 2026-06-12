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
    
    # Adversarial review: challenge each agent's output, adjust confidence
    confidence = adversarial_review(valid, conflicts, consensus)
    
    # Odds timeline analysis: how fresh/stale are the odds?
    timeline = analyse_odds_timeline(valid)
    
    # Data sufficiency: what to do when data is incomplete
    guidance = data_sufficiency_guidance(valid, confidence, timeline)
    
    # Build bet recommendations (uses adjusted confidence + timeline)
    bets = build_bet_recommendations(valid, conflicts, consensus, confidence, timeline)
    
    # Build executive summary
    summary = build_summary(valid, conflicts, consensus, bets, confidence, timeline, guidance)
    
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
        "confidence": confidence,
        "timeline": timeline,
        "guidance": guidance,
        "bets": bets,
        "summary": summary,
        "warnings": [e.get("error", "") for e in errors],
    }


def adversarial_review(valid_results: list[dict], conflicts: list[dict], consensus: list[dict]) -> dict:
    """Challenge each agent's output for statistical validity, data quality, and logical consistency.
    
    Returns confidence adjustments per agent: {agent_name: {adjusted_strength, challenges, downgrade_reasons}}
    """
    challenges = {}
    
    for r in valid_results:
        agent = r["agent"]
        metrics = r.get("key_metrics", {})
        strength = r.get("signal_strength", "weak")
        downgrades = []
        upgrades = []
        
        # --- A: fundamentals ---
        if agent == "fundamentals":
            gap = metrics.get("gap")
            h2h_total = metrics.get("h2h_total_matches", 0)
            home_matches = metrics.get("home_form_score") is not None
            away_matches_analysed = metrics.get("away_form_score", 0)
            
            if gap is not None and abs(gap) < 0.03:
                downgrades.append(f"Gap ({gap:.3f}) within noise margin (<3%). Not a real deviation.")
            if gap is not None and abs(gap) > 0.25:
                downgrades.append(f"Gap ({gap:.3f}) is extreme. Possible data anomaly, not fundamental insight.")
            if h2h_total < 5:
                downgrades.append(f"H2H sample too small (N={h2h_total}). H2H weight should be near zero.")
            if h2h_total == 0:
                downgrades.append("No H2H data — fundamentals model missing key input. Reduce confidence.")
            if not home_matches:
                downgrades.append("Insufficient form data for home team.")
            
            # Home advantage overclaimed? Only if both sample sizes good
            if gap is not None and h2h_total >= 10 and abs(gap) > 0.08:
                upgrades.append(f"Large gap ({gap:.3f}) with solid H2H sample (N={h2h_total}). Signal credible.")
        
        # --- B: odds_signals ---
        elif agent == "odds_signals":
            mw = metrics.get("match_winner", {})
            ah = metrics.get("asian_handicap", {})
            ou = metrics.get("over_under", {})
            overround = metrics.get("overround")
            rate = metrics.get("return_rate")
            
            if not mw.get("home"):
                downgrades.append("No 1X2 odds available — market not yet formed. Zero signal.")
            if not ah.get("line") or ah.get("line") == "N/A":
                downgrades.append("No Asian handicap data. Spread market unavailable for this fixture.")
            if overround is not None and overround > 0.10:
                downgrades.append(f"High overround ({overround:.1%}). Wide bookmaker margin dilutes signal.")
            if rate is not None and rate > 0.97:
                downgrades.append(f"Return rate {rate:.1%} suspiciously high. Possible stale or bad data.")
            if rate is not None and rate < 0.85:
                downgrades.append(f"Return rate {rate:.1%} very low. Market is inefficient — high uncertainty.")
            if all(v is None for v in mw.values()):
                downgrades.append("All 1X2 odds missing. Cannot assess bookmaker intent.")
            
            if overround is not None and overround < 0.04 and mw.get("home"):
                upgrades.append(f"Very sharp market (overround {overround:.1%}). Odds signal is reliable.")
        
        # --- C: historical_backtest ---
        elif agent == "historical_backtest":
            baseline = metrics.get("league_baseline", {})
            n = baseline.get("total_matches", 0)
            
            if n < 20:
                downgrades.append(f"Baseline sample too small (N={n}). Statistical noise dominates.")
            if n < 50 and n >= 20:
                downgrades.append(f"Small baseline (N={n}). Moderate uncertainty — interpret with caution.")
            if n >= 100:
                upgrades.append(f"Large historical baseline (N={n}). Baseline statistics are reliable.")
            if n == 0:
                downgrades.append("No historical data available. Backtest is empty — ignore this agent.")
        
        # --- D: bookmaker_divergence ---
        elif agent == "bookmaker_divergence":
            bm_count = metrics.get("bookmaker_count", 0)
            mw_div = metrics.get("match_winner_divergence", {})
            mw_level = mw_div.get("level", "none")
            
            if bm_count < 5:
                downgrades.append(f"Only {bm_count} bookmakers. Divergence stats unreliable with N<5.")
            if bm_count == 0:
                downgrades.append("Zero bookmakers available. No divergence data.")
            if mw_level == "none":
                downgrades.append("No match winner divergence data. Market may not be formed.")
        
        # --- E: market_sentiment ---
        elif agent == "market_sentiment":
            heat = metrics.get("overheat_level", "low")
            preds = metrics.get("predictions", {})
            bias = metrics.get("public_bias_analysis", {})
            bias_signals = 0
            for outcome_data in bias.values():
                if isinstance(outcome_data, dict) and outcome_data.get("bias") != "neutral":
                    bias_signals += 1
            
            if bias_signals == 0:
                downgrades.append("No public bias detected. Either market is balanced or data insufficient.")
            if not preds:
                downgrades.append("No prediction data from API-Football. Weak sentiment analysis.")
            if heat == "low" and bias_signals == 0:
                downgrades.append("No overheating and no bias — sentiment analysis adds no information.")
            if heat == "high" and bias_signals == 0:
                downgrades.append(f"Heat level '{heat}' but zero bias signals — contradictory. Data may be unreliable.")
        
        # --- F: objective_factors ---
        elif agent == "objective_factors":
            home_inj = metrics.get("home", {}).get("injuries", 0)
            away_inj = metrics.get("away", {}).get("injuries", 0)
            
            if home_inj == 0 and away_inj == 0:
                downgrades.append("No injuries reported. Either both squads are fully fit OR data is incomplete (check league coverage).")
            if home_inj > 5 or away_inj > 5:
                downgrades.append(f"Very high injury count ({home_inj}+{away_inj}). Possible data quality issue, not real injury crisis.")
        
        # --- G: tactical_matchup ---
        elif agent == "tactical_matchup":
            clash = metrics.get("style_clash", {})
            home_style = metrics.get("home", {}).get("style", {})
            away_style = metrics.get("away", {}).get("style", {})
            matches_home = home_style.get("matches_analysed", 0)
            matches_away = away_style.get("matches_analysed", 0)
            
            if matches_home < 3:
                downgrades.append(f"Home style based on only {matches_home} matches. Style inference unreliable.")
            if matches_away < 3:
                downgrades.append(f"Away style based on only {matches_away} matches. Style inference unreliable.")
            if clash.get("clash_count", 0) == 0 and clash.get("advantage_count", 0) == 0:
                downgrades.append("No tactical clashes or advantages detected. Style analysis adds no edge for this fixture.")
            if not home_style.get("avg_possession") and not away_style.get("avg_possession"):
                downgrades.append("No possession data available. Style analysis is guesswork without it.")
        
        # --- H: player_coach_xg ---
        elif agent == "player_coach_xg":
            coaches = metrics.get("coaches", {})
            xg_source = metrics.get("xg_source", {})
            home_coach = coaches.get("home", {})
            away_coach = coaches.get("away", {})
            
            if not home_coach.get("available") and not away_coach.get("available"):
                downgrades.append("Coach data unavailable for both teams. Coach analysis is empty.")
            if xg_source.get("source") == "fallback":
                downgrades.append(f"xG not available ({xg_source.get('note', 'unknown')[:60]}). Using goals/game proxy — large error margin.")
            if xg_source.get("source") == "understat" and not xg_source.get("data_available"):
                downgrades.append("Understat xG returned no data for this league/season.")
            if xg_source.get("source") == "unavailable":
                downgrades.append("xG not available for this league. Ignore xG-based findings.")
        
        # Downgrade strength if challenges found
        if len(downgrades) >= 3:
            adjusted = "weak"
        elif len(downgrades) >= 1:
            strength_map = {"strong": "medium", "medium": "weak", "weak": "weak", "none": "none"}
            adjusted = strength_map.get(strength, "weak")
        elif len(upgrades) >= 2:
            strength_map = {"weak": "medium", "medium": "strong", "strong": "strong", "none": "weak"}
            adjusted = strength_map.get(strength, "none")
        else:
            adjusted = strength
        
        challenges[agent] = {
            "original_strength": strength,
            "adjusted_strength": adjusted,
            "downgraded": adjusted != strength and adjusted == "weak" and strength != "weak",
            "downgrade_reasons": downgrades,
            "upgrade_reasons": upgrades,
        }
    
    return challenges


def analyse_odds_timeline(valid_results: list[dict]) -> dict:
    """Analyze odds freshness: how close to kickoff? When was last update?
    
    Odds 3 days before kickoff = very early market, likely to shift.
    Odds 10 minutes before kickoff = late market, sharp signal.
    Odds not updated in hours = stale data, unreliable.
    """
    from datetime import datetime, timezone, timedelta
    
    # Extract fixture time from any agent that has it (odds_signals usually)
    commence_time = None
    last_update = None
    
    for r in valid_results:
        if r["agent"] == "odds_signals":
            # The Odds API returns commence_time in the odds response
            # We don't have it directly, but we can check notes
            notes = r.get("notes", [])
            for note in notes:
                if "kickoff" in note.lower() or "commence" in note.lower():
                    pass
            break
    
    # Use API-Football fixture date if available from fundamentals or objective_factors
    for r in valid_results:
        metrics = r.get("key_metrics", {})
        # Check for fixture date in any metrics
        fixture_date = metrics.get("fixture_date")
        if fixture_date:
            try:
                commence_time = datetime.fromisoformat(fixture_date.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
    
    now = datetime.now(timezone.utc)
    hours_to_kickoff = None
    
    # Analyze based on what we know
    findings = []
    
    # Check if odds data is from The Odds API (sub-agents B, D)
    has_odds_data = any(
        r["agent"] in ("odds_signals", "bookmaker_divergence")
        and "error" not in r
        for r in valid_results
    )
    
    if not has_odds_data:
        findings.append("No odds data available — market not yet formed. All odds-based analysis is unreliable.")
        return {
            "odds_available": False,
            "market_phase": "pre-market",
            "reliability": "none",
            "findings": findings,
            "action": "Wait for odds to be published. Re-analyze when bookmakers list this fixture.",
        }
    
    # Staleness check: does market_sentiment or odds_signals show data
    # The Odds API has last_update per bookmaker — but we aggregate, so check freshness
    findings.append("Checking odds freshness across sub-agents...")
    
    # If we can determine fixture is within 2 hours
    if commence_time:
        hours_to_kickoff = (commence_time - now).total_seconds() / 3600
        
        if hours_to_kickoff < 0:
            phase = "in-play"
            reliability = "medium"  # In-play odds change fast
            findings.append(f"Fixture is IN-PLAY. Odds are live but volatile. Lock in bets quickly or wait for halftime.")
        elif hours_to_kickoff < 2:
            phase = "late-market"
            reliability = "strong"
            findings.append(f"{hours_to_kickoff:.1f}h to kickoff. Late market — odds movement is most informative. Strong signal.")
        elif hours_to_kickoff < 12:
            phase = "mid-market"
            reliability = "medium"
            findings.append(f"{hours_to_kickoff:.1f}h to kickoff. Mid-market. Odds reasonably settled but may still shift on team news.")
        elif hours_to_kickoff < 48:
            phase = "early-market"
            reliability = "weak"
            findings.append(f"{hours_to_kickoff:.1f}h to kickoff. Early market. Odds likely to move significantly. Recommend re-analysis closer to kickoff.")
        else:
            phase = "pre-market"
            reliability = "none"
            findings.append(f"{hours_to_kickoff:.1f}h to kickoff. Very early. Odds are preliminary — do NOT bet based on current prices.")
    else:
        phase = "unknown"
        reliability = "medium"
        findings.append("Cannot determine kickoff time. Assuming mid-market reliability. Verify fixture date before betting.")
    
    # Check for data staleness across the board
    all_stale = all(
        r.get("signal_strength") == "weak" or r.get("signal_strength") == "none"
        for r in valid_results if "error" not in r
    )
    if all_stale:
        findings.append("All agents report weak signals — overall data quality is low for this fixture.")
        if reliability != "none":
            reliability = "weak"
    
    # Action guidance based on phase
    if phase in ("pre-market", "early-market"):
        action = "WAIT. Odds will shift significantly. Re-analyze 2-4 hours before kickoff for meaningful signals."
    elif phase == "in-play":
        action = "CAUTION. In-play odds are volatile. Use halftime analysis rather than pre-match recommendations."
    elif phase == "mid-market":
        action = "Monitor for late movements. Current odds are informative but not final."
    else:
        action = "Odds signals are at peak informativeness. Proceed with analysis."
    
    return {
        "odds_available": True,
        "market_phase": phase,
        "hours_to_kickoff": round(hours_to_kickoff, 1) if commence_time and hours_to_kickoff else None,
        "reliability": reliability,
        "findings": findings,
        "action": action,
    }


def data_sufficiency_guidance(valid_results: list[dict], confidence: dict, timeline: dict) -> dict:
    """When data is incomplete, provide actionable guidance instead of just flagging issues.
    
    Returns structured advice: what to trust, what to ignore, and what to wait for.
    """
    agents_ok = []
    agents_unreliable = []
    agents_empty = []
    
    for r in valid_results:
        agent = r["agent"]
        if "error" in r:
            agents_empty.append((agent, r.get("error", "unknown error")))
            continue
        
        conf = confidence.get(agent, {})
        if conf.get("adjusted_strength") == "weak" and conf.get("downgraded", False):
            agents_unreliable.append((agent, conf.get("downgrade_reasons", [])))
        elif conf.get("adjusted_strength") in ("strong", "medium"):
            agents_ok.append(agent)
        else:
            agents_unreliable.append((agent, conf.get("downgrade_reasons", [])))
    
    n_ok = len(agents_ok)
    n_total = len(valid_results)
    
    # Build guidance
    guidance_parts = []
    
    # Trust these agents
    if agents_ok:
        names = ", ".join(a for a in agents_ok)
        guidance_parts.append(f"TRUST ({n_ok}/{n_total}): {names} — these have sufficient data quality. Weight their findings higher.")
    else:
        guidance_parts.append(f"TRUST (0/{n_total}): No agents have sufficient data quality. Treat ALL findings as speculative.")
    
    # Ignore these agents
    if agents_unreliable:
        for agent, reasons in agents_unreliable:
            top_reason = reasons[0] if reasons else "unknown issue"
            guidance_parts.append(f"DOWNGRADE [{agent}]: {top_reason}")
    
    # Empty agents
    if agents_empty:
        for agent, err in agents_empty:
            guidance_parts.append(f"MISSING [{agent}]: {err[:100]}")
    
    # Overall action
    market_phase = timeline.get("market_phase", "unknown")
    odds_reliability = timeline.get("reliability", "medium")
    
    if n_ok == 0 and market_phase in ("pre-market", "early-market"):
        overall = "WAIT. No reliable agents AND odds are early. Re-analyze closer to kickoff."
    elif n_ok == 0:
        overall = "AVOID. No agents have sufficient data. Betting on this fixture is gambling, not analysis."
    elif n_ok <= 2 and odds_reliability == "weak":
        overall = f"CAUTION. Only {n_ok} agents reliable AND odds signals are weak. Reduce stake or wait."
    elif n_ok <= 3:
        overall = f"TENTATIVE. Only {n_ok}/{n_total} agents reliable. Use recommendations as directional, not conviction bets."
    elif n_ok >= 5:
        overall = f"SOLID. {n_ok}/{n_total} agents reliable. Analysis has sufficient data foundation."
    else:
        overall = f"MODERATE. {n_ok}/{n_total} agents reliable. Standard confidence."
    
    return {
        "reliable_agents": agents_ok,
        "unreliable_agents": [a for a, _ in agents_unreliable],
        "empty_agents": [a for a, _ in agents_empty],
        "reliable_count": n_ok,
        "total_count": n_total,
        "guidance": guidance_parts,
        "overall_action": overall,
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
                               consensus: list[dict],
                               confidence: dict,
                               timeline: dict) -> dict:
    """Build final bet type recommendations with adversarial confidence + timeline adjustment."""
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
    
    # Timeline adjustment: early market = lower confidence
    market_phase = timeline.get("market_phase", "unknown")
    odds_stale = market_phase in ("pre-market", "early-market")
    in_play = market_phase == "in-play"
    
    # Aggregate ADJUSTED signal strengths (after adversarial review)
    adjusted_strengths = [
        confidence.get(r["agent"], {}).get("adjusted_strength", "weak")
        for r in valid_results if "error" not in r
    ]
    strong_count = sum(1 for s in adjusted_strengths if s == "strong")
    medium_count = sum(1 for s in adjusted_strengths if s == "medium")
    
    # Count how many agents were downgraded
    downgraded_count = sum(
        1 for r in valid_results if "error" not in r
        and confidence.get(r["agent"], {}).get("downgraded", False)
    )
    
    # Decision logic
    if not valid_results:
        bets["1x2"]["recommendation"] = "avoid"
        bets["1x2"]["confidence"] = "high"
        bets["1x2"]["reasoning"] = "No valid agent results — cannot recommend"
    elif odds_stale:
        bets["1x2"]["recommendation"] = "watch"
        bets["1x2"]["confidence"] = "low"
        bets["1x2"]["reasoning"] = f"Market is {market_phase} — odds will shift. Re-analyze closer to kickoff."
    elif in_play:
        bets["1x2"]["recommendation"] = "watch"
        bets["1x2"]["confidence"] = "low"
        bets["1x2"]["reasoning"] = "In-play — odds are volatile. Use halftime data, not pre-match analysis."
    elif downgraded_count >= 5:
        bets["1x2"]["recommendation"] = "avoid"
        bets["1x2"]["confidence"] = "high"
        bets["1x2"]["reasoning"] = f"{downgraded_count}/{len(valid_results)} agents downgraded — data quality too low"
    elif has_consensus and strong_consensus and not has_conflict and downgraded_count <= 2:
        bets["1x2"]["recommendation"] = "recommend"
        bets["1x2"]["confidence"] = "high"
        bets["1x2"]["reasoning"] = "Strong multi-agent consensus, minimal adversarial challenges"
    elif has_consensus and strong_consensus and downgraded_count <= 3:
        bets["1x2"]["recommendation"] = "recommend"
        bets["1x2"]["confidence"] = "medium"
        bets["1x2"]["reasoning"] = f"Consensus exists but {downgraded_count} agents have data quality concerns"
    elif has_consensus and has_conflict:
        bets["1x2"]["recommendation"] = "watch"
        bets["1x2"]["confidence"] = "medium"
        bets["1x2"]["reasoning"] = "Consensus exists but conflicts present — monitor odds movement"
    elif high_conflict or downgraded_count >= 4:
        bets["1x2"]["recommendation"] = "avoid"
        bets["1x2"]["confidence"] = "high"
        bets["1x2"]["reasoning"] = f"Major conflicts or {downgraded_count} data quality issues — unreliable signals"
    elif strong_count >= 5:
        bets["1x2"]["recommendation"] = "recommend"
        bets["1x2"]["confidence"] = "medium"
        bets["1x2"]["reasoning"] = "Majority of agents show strong signals after adversarial review"
    elif medium_count + strong_count >= 5:
        bets["1x2"]["recommendation"] = "watch"
        bets["1x2"]["confidence"] = "medium"
        bets["1x2"]["reasoning"] = "Moderate signals from majority — worth monitoring"
    
    # Asian handicap follows 1X2 logic loosely
    bets["asian_handicap"]["recommendation"] = bets["1x2"]["recommendation"]
    bets["asian_handicap"]["confidence"] = bets["1x2"]["confidence"]
    bets["asian_handicap"]["reasoning"] = "Follows 1X2 analysis; check odds_signals for AH-specific data"
    
    # Over/Under
    ou_downgraded = confidence.get("player_coach_xg", {}).get("downgraded", False)
    if ou_downgraded:
        bets["over_under"]["recommendation"] = "watch"
        bets["over_under"]["confidence"] = "low"
        bets["over_under"]["reasoning"] = "xG data unavailable — over/under analysis unreliable"
    else:
        ou_agents = [r for r in valid_results if "over" in r.get("finding", "").lower() or "under" in r.get("finding", "").lower()]
        if len(ou_agents) >= 2:
            bets["over_under"]["recommendation"] = "recommend"
            bets["over_under"]["confidence"] = "medium"
            bets["over_under"]["reasoning"] = "Multiple agents agree on O/U direction"
    
    return bets


def build_summary(valid_results: list[dict], conflicts: list[dict],
                   consensus: list[dict], bets: dict, confidence: dict,
                   timeline: dict, guidance: dict) -> str:
    """Build executive summary text."""
    parts = []
    
    # Timeline header
    phase = timeline.get("market_phase", "unknown")
    hours = timeline.get("hours_to_kickoff")
    if hours is not None:
        parts.append(f"MARKET PHASE: {phase} ({hours}h to kickoff) — {timeline.get('action', '')}")
    else:
        parts.append(f"MARKET PHASE: {phase} — {timeline.get('action', '')}")
    parts.append("")
    
    # Agent summary with adversarial adjustment
    for r in valid_results:
        strength = r.get("signal_strength", "none")
        agent_name = r["agent"]
        conf = confidence.get(agent_name, {})
        adjusted = conf.get("adjusted_strength", strength)
        downgrades = conf.get("downgrade_reasons", [])
        
        if adjusted != strength:
            parts.append(f"[{agent_name}] {strength}→{adjusted} {r.get('finding', 'No finding')}")
            for d in downgrades[:2]:
                parts.append(f"  ⚠ {d}")
        else:
            parts.append(f"[{agent_name}] ({strength}) {r.get('finding', 'No finding')}")
    
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
    
    # Data Sufficiency Guidance
    parts.append(f"\n=== DATA SUFFICIENCY ===")
    parts.append(f"  {guidance.get('overall_action', '')}")
    for g in guidance.get("guidance", []):
        parts.append(f"  {g}")
    
    # Adversarial review summary
    downgraded_agents = [a for a, c in confidence.items() if c.get("downgraded")]
    if downgraded_agents:
        parts.append(f"\n=== ADVERSARIAL REVIEW ({len(downgraded_agents)} agents flagged) ===")
        for a in downgraded_agents:
            reasons = confidence[a].get("downgrade_reasons", [])
            parts.append(f"  [{a}] {len(reasons)} issue(s):")
            for r in reasons:
                parts.append(f"    - {r}")
    
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
