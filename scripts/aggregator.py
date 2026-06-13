"""Aggregator — synthesise odds + lineups + external analysis into predictions.

Produces:
  1X2 probabilities, Asian Handicap, Correct Score, Over/Under
  Upset analysis, market inconsistencies, recommendations

Usage:
    python aggregator.py <odds_json_file> <flashscore_json_file>
"""

import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def aggregate(odds: dict, flashscore: dict | None, external: dict | None = None) -> dict:
    """Synthesise predictions from odds + lineup + external analysis."""
    match = odds.get("match", {})
    markets = odds.get("markets", {})
    had = markets.get("had", {})
    hhad = markets.get("hhad", {})
    crs = markets.get("correct_score", {})
    hafu = markets.get("half_time_full_time", {})
    ttg = markets.get("total_goals", {})
    signals = odds.get("signals", [])

    home = match.get("home_team", "Home")
    away = match.get("away_team", "Away")
    match_num = match.get("match_num", "")
    match_date = match.get("match_date", "")

    # ── 1X2 Prediction ──
    x12 = {"home": 33, "draw": 33, "away": 33, "prediction": "Draw", "confidence": "none"}
    if had.get("available"):
        fp = had.get("fair_probability", {})
        x12 = {
            "home": round(fp.get("home", 0.33) * 100),
            "draw": round(fp.get("draw", 0.33) * 100),
            "away": round(fp.get("away", 0.33) * 100),
            "prediction": had.get("prediction", ""),
            "overround": round(had.get("overround", 0) * 100, 1),
            "confidence": "high" if max(fp.values(), default=0) > 0.50 else "medium",
        }

    # If external analysis provides adjusted probabilities, override
    if external and external.get("adjusted_1x2"):
        adj = external["adjusted_1x2"]
        total = sum(adj.values())
        x12["home"] = round(adj.get("home", 0) / total * 100)
        x12["draw"] = round(adj.get("draw", 0) / total * 100)
        x12["away"] = round(adj.get("away", 0) / total * 100)
        x12["prediction"] = max(adj, key=adj.get) if total > 0 else x12["prediction"]
        x12["adjusted_by"] = "external_analysis"
        x12["confidence"] = "medium"

    # ── Asian Handicap Prediction ──
    ah = {"available": False, "line": "N/A", "recommendation": "N/A", "overround": None}
    if hhad.get("available"):
        fp = hhad.get("fair_probability", {})
        ah = {
            "available": True,
            "line": hhad.get("line", "N/A"),
            "odds": hhad.get("odds", {}),
            "fair_probability": {k: round(v * 100, 1) for k, v in fp.items()},
            "prediction": hhad.get("prediction", ""),
            "overround": round(hhad.get("overround", 0) * 100, 1),
        }

    # ── Correct Score Prediction ──
    scores = {"available": False, "most_likely": "", "top_5": []}
    if crs.get("available"):
        scores = {
            "available": True,
            "most_likely": crs.get("most_likely", {}),
            "top_5": crs.get("top_5_scores", []),
            "overround": round(crs.get("overround", 0) * 100, 1),
        }

    # ── Over/Under Prediction ──
    ou = {"available": False, "line": "2.5", "over": 50, "under": 50}
    if ttg.get("available"):
        ou = {
            "available": True,
            "over_2_5": round(ttg.get("over_2_5_probability", 0.5) * 100),
            "under_2_5": round(ttg.get("under_2_5_probability", 0.5) * 100),
            "most_likely": ttg.get("most_likely", ""),
            "goals_detail": ttg.get("fair_probability", {}),
            "overround": round(ttg.get("overround", 0) * 100, 1),
        }

    # ── HT/FT Prediction ──
    htft = {"available": False, "prediction": ""}
    if hafu.get("available"):
        htft = {
            "available": True,
            "prediction": hafu.get("prediction", ""),
            "top_3": hafu.get("top_3", []),
            "overround": round(hafu.get("overround", 0) * 100, 1),
        }

    # ── Upset Detection ──
    upset = detect_upset(had, hhad, hafu, ttg, flashscore, external)

    # ── Build Summary ──
    summary_parts = []
    summary_parts.append(f"MATCH: {match_num} {home} vs {away} ({match_date})")

    if x12["confidence"] != "none":
        summary_parts.append(f"1X2: {home} {x12['home']}% / Draw {x12['draw']}% / {away} {x12['away']}% -> {x12['prediction']} [{x12['confidence']}]")
    if ah["available"]:
        summary_parts.append(f"AH ({ah['line']}): {ah['prediction']} — {ah['fair_probability']}")
    if scores["available"]:
        ms = scores["most_likely"]
        summary_parts.append(f"Scores: most likely {ms.get('score', '?')} ({ms.get('fair_probability', 0)*100:.1f}%)")
        top5_str = " ".join(f"{s['score']}({s['fair_probability']*100:.0f}%)" for s in scores["top_5"])
        summary_parts.append(f"Top 5: {top5_str}")
    if ou["available"]:
        summary_parts.append(f"O/U 2.5: Over {ou['over_2_5']}% / Under {ou['under_2_5']}%")
    if htft["available"]:
        summary_parts.append(f"HT/FT: {htft['prediction']} — {[t['outcome']+' '+str(t['fair_probability']*100)[:4]+'%' for t in htft['top_3']]}")
    if upset.get("signals"):
        summary_parts.append(f"UPSET: {'; '.join(upset['signals'])}")
    if upset.get("recommendation"):
        summary_parts.append(f"UPSET LEVEL: {upset['recommendation']}")

    # ── Flashscore context ──
    flash_lines = []
    if flashscore and flashscore.get("available"):
        for team, formation in flashscore.get("formations", {}).items():
            flash_lines.append(f"{team}: {formation}")
        for team, xi in flashscore.get("starting_xi", {}).items():
            names = [p["name"] for p in xi[:5]]
            flash_lines.append(f"{team} XI: {', '.join(names)}...")
        for inj in flashscore.get("injuries", []):
            flash_lines.append(f"Injury: {inj['team']} - {inj['player']} ({inj['reason']})")

    return {
        "match": match,
        "predictions": {
            "1x2": x12,
            "asian_handicap": ah,
            "correct_score": scores,
            "over_under": ou,
            "half_time_full_time": htft,
        },
        "upset": upset,
        "data_sources": {
            "odds": bool(markets.get("had", {}).get("available")),
            "flashscore": bool(flashscore and flashscore.get("available")),
            "external_analysis": bool(external),
        },
        "flashscore_context": flash_lines,
        "market_signals": signals,
        "summary": "\n".join(summary_parts),
    }


def detect_upset(had: dict, hhad: dict, hafu: dict, ttg: dict,
                 flashscore: dict | None, external: dict | None) -> dict:
    """Detect where the market might be wrong and an upset could happen."""
    signals = []
    score = 0  # 0-10, higher = more upset potential

    # 1. Deep handicap but low HAD conviction
    if hhad.get("available") and had.get("available"):
        hh_line = hhad.get("line", "")
        had_fp = had.get("fair_probability", {})
        try:
            line_val = abs(float(hh_line))
            fav_prob = max(had_fp.values())
            if line_val >= 1.0 and fav_prob < 0.55:
                signals.append(f"Deep AH ({hh_line}) but 1X2 only {fav_prob*100:.0f}% — market may be overconfident")
                score += 2
            if line_val >= 2.0:
                signals.append(f"Very deep AH ({hh_line}) — favorite needs 3+ goal win to cover")
                score += 1
        except (ValueError, TypeError):
            pass

    # 2. HT/FT vs HAD disagreement
    if hafu.get("available") and had.get("available"):
        hafu_pred = hafu.get("prediction", "")
        had_pred = had.get("prediction", "")
        if hafu_pred and had_pred:
            hafu_winner = hafu_pred.split("/")[-1] if "/" in hafu_pred else ""
            if hafu_winner != had_pred:
                signals.append(f"HT/FT says {hafu_pred} but HAD says {had_pred} — time-of-scoring mismatch")
                score += 1

    # 3. Over 2.5 vs correct score consensus
    if ttg.get("available"):
        over = ttg.get("over_2_5_probability", 0)
        under = ttg.get("under_2_5_probability", 0)
        if 0.40 <= over <= 0.45:
            signals.append(f"O2.5 probability {over*100:.0f}% is marginal — goals market is uncertain")
            score += 1
        if over < 0.35:
            signals.append(f"O2.5 only {over*100:.0f}% — market expects very low-scoring match")
            score += 1

    # 4. Injury impact not reflected
    if flashscore and flashscore.get("injuries"):
        inj = flashscore.get("injuries", [])
        if len(inj) >= 2:
            signals.append(f"{len(inj)} injuries reported — may not be fully priced into odds")
            score += 2

    # 5. External analysis suggests upset
    if external and external.get("upset_indicators"):
        for ind in external["upset_indicators"]:
            signals.append(ind)
            score += 1

    if score >= 5:
        level = "high"
    elif score >= 3:
        level = "medium"
    elif score >= 1:
        level = "low"
    else:
        level = "none"

    return {
        "upset_score": score,
        "level": level,
        "signals": signals,
        "recommendation": "Consider opposing the favorite" if score >= 4 else
                         "Monitor for upset signals" if score >= 2 else
                         "No clear upset signals",
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: aggregator.py <odds.json> [flashscore.json]"}))
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        odds = json.load(f)

    flashscore = None
    if len(sys.argv) >= 3:
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            flashscore = json.load(f)

    result = aggregate(odds, flashscore)
    print(json.dumps(result, ensure_ascii=False, indent=2))
