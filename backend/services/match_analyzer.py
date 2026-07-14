"""
LoL Stats - Match Analyzer
===========================
Analyzes match data to generate personalized improvement feedback.

Analysis dimensions:
  1. CS — creep score vs role/rank benchmarks
  2. KP — kill participation percentage
  3. Vision — vision score, ward usage
  4. Deaths — death patterns and avoidable deaths
  5. Itemization — build appropriateness

Returns a dict with sections for each dimension plus an overall grade.
"""

import logging

logger = logging.getLogger(__name__)

# ─── Role Benchmarks (approximate, for support role) ───────
# Format: {position: {cs_per_min, kp_percent, vision_per_min, ...}}
# These are rough averages — can be refined over time.

BENCHMARKS = {
    "UTILITY": {  # Support
        "cs_per_min": 0.5,       # Supports don't CS much
        "kp_target": 60,          # Kill participation % (should be high)
        "vision_per_min": 1.5,    # Vision score per minute
        "control_wards_per_game": 3,
        "deaths_per_game_target": 5,
        "damage_share": 10,       # % of team damage
        "gold_per_min": 250,
    },
    "BOTTOM": {  # ADC
        "cs_per_min": 7.0,
        "kp_target": 55,
        "vision_per_min": 0.5,
        "control_wards_per_game": 1,
        "deaths_per_game_target": 3,
        "damage_share": 25,
        "gold_per_min": 400,
    },
    "MIDDLE": {
        "cs_per_min": 6.5,
        "kp_target": 55,
        "vision_per_min": 0.7,
        "control_wards_per_game": 2,
        "deaths_per_game_target": 3,
        "damage_share": 22,
        "gold_per_min": 380,
    },
    "JUNGLE": {
        "cs_per_min": 5.0,
        "kp_target": 60,
        "vision_per_min": 1.0,
        "control_wards_per_game": 2,
        "deaths_per_game_target": 4,
        "damage_share": 18,
        "gold_per_min": 330,
    },
    "TOP": {
        "cs_per_min": 6.0,
        "kp_target": 45,
        "vision_per_min": 0.6,
        "control_wards_per_game": 1,
        "deaths_per_game_target": 4,
        "damage_share": 20,
        "gold_per_min": 360,
    },
}

# Fallback for unknown positions
_DEFAULT_BENCHMARKS = {
    "cs_per_min": 5.0,
    "kp_target": 50,
    "vision_per_min": 0.8,
    "control_wards_per_game": 1,
    "deaths_per_game_target": 4,
    "damage_share": 18,
    "gold_per_min": 330,
}


def analyze_match(match_row: dict, timeline_events: list[dict] | None = None) -> dict:
    """
    Analyze a single match and return structured improvement feedback.

    Args:
        match_row: Dict with match data (from SQLite row or Riot API).
        timeline_events: Optional list of timeline event dicts.

    Returns:
        Dict with analysis sections and overall grade.
    """
    position = match_row.get("individual_position") or "UTILITY"
    benches = BENCHMARKS.get(position, _DEFAULT_BENCHMARKS)

    game_minutes = max(match_row.get("game_duration", 0) / 60, 1)  # Avoid div by zero

    # Compute core metrics
    cs = match_row.get("total_minions_killed", 0) + match_row.get("neutral_minions_killed", 0)
    cs_per_min = cs / game_minutes
    vision_score = match_row.get("vision_score", 0)
    vision_per_min = vision_score / game_minutes
    k = match_row.get("kills", 0)
    d = match_row.get("deaths", 0)
    a = match_row.get("assists", 0)

    # ── CS Analysis ──
    cs_status, cs_score, cs_details = _analyze_cs(cs_per_min, position, benches)

    # ── Kill Participation ──
    # We don't have team kills from a single participant row, so estimate
    # or use benchmarks as baseline
    kp_status, kp_score, kp_details = _analyze_kp(k, d, a, position, benches)

    # ── Vision Analysis ──
    control_wards = match_row.get("control_wards_placed", 0)
    vision_status, vision_score_pct, vision_details = _analyze_vision(
        vision_per_min, control_wards, position, benches
    )

    # ── Death Analysis ──
    death_status, death_score, death_details = _analyze_deaths(d, game_minutes, position, benches)

    # ── Itemization Analysis ──
    items = [match_row.get(f"item{i}", 0) for i in range(7)]
    item_status, item_score, item_details = _analyze_items(items, position, match_row)

    # ── Overall Grade ──
    scores = [cs_score, kp_score, vision_score_pct, death_score, item_score]
    avg_score = sum(scores) / len(scores) if scores else 50

    if avg_score >= 85:
        grade = "S"
    elif avg_score >= 70:
        grade = "A"
    elif avg_score >= 55:
        grade = "B"
    elif avg_score >= 40:
        grade = "C"
    else:
        grade = "D"

    # Focus areas (lowest scoring dimensions)
    focus_map = {
        "CS": cs_score, "Kill Participation": kp_score,
        "Vision": vision_score_pct, "Deaths": death_score,
        "Itemization": item_score,
    }
    sorted_focus = sorted(focus_map.items(), key=lambda x: x[1])
    focus_areas = []
    for area, s in sorted_focus[:3]:
        if s < 70:
            if area == "CS":
                focus_areas.append(f"Improve CS — aim for {benches['cs_per_min']} CS/min")
            elif area == "Kill Participation":
                focus_areas.append(f"Increase kill participation — target {benches['kp_target']}%")
            elif area == "Vision":
                focus_areas.append(f"Improve vision control — place more wards")
            elif area == "Deaths":
                focus_areas.append(f"Reduce unnecessary deaths — review death timestamps")
            elif area == "Itemization":
                focus_areas.append(f"Optimize item build — check recommended items")

    win = match_row.get("win", False)
    summary = _generate_summary(grade, avg_score, focus_areas, bool(win))

    return {
        "match_id": match_row.get("match_id", ""),
        "champion_name": match_row.get("champion_name", ""),
        "position": position,
        "win": bool(win),
        "game_duration": match_row.get("game_duration", 0),
        "cs": {
            "status": cs_status,
            "score": cs_score,
            "details": cs_details,
            "benchmarks": {"cs_per_min_target": benches["cs_per_min"]},
        },
        "kill_participation": {
            "status": kp_status,
            "score": kp_score,
            "details": kp_details,
            "benchmarks": {"kp_target": benches["kp_target"]},
        },
        "vision": {
            "status": vision_status,
            "score": vision_score_pct,
            "details": vision_details,
            "benchmarks": {
                "vision_per_min_target": benches["vision_per_min"],
                "control_wards_target": benches["control_wards_per_game"],
            },
        },
        "deaths": {
            "status": death_status,
            "score": death_score,
            "details": death_details,
            "benchmarks": {"deaths_per_game_target": benches["deaths_per_game_target"]},
        },
        "itemization": {
            "status": item_status,
            "score": item_score,
            "details": item_details,
        },
        "overall_grade": grade,
        "focus_areas": focus_areas,
        "summary": summary,
    }


def _analyze_cs(cs_per_min: float, position: str, benches: dict) -> tuple[str, int, list[str]]:
    target = benches["cs_per_min"]
    details = [f"CS/min: {cs_per_min:.1f} (target: {target} for {position})"]

    if position == "UTILITY":
        # Supports shouldn't need high CS — check if they're taking too much
        if cs_per_min > 2.0:
            return "warning", 60, details + [
                "⚠️ As support, you're taking more CS than expected. Are you taking your ADC's farm?",
                "Focus on letting your ADC last-hit while you harass and ward.",
            ]
        return "ok", 90, details + [
            "✅ Appropriate CS for support role.",
            "Your gold should come from support item and assists, not minions.",
        ]

    if cs_per_min >= target * 1.1:
        return "ok", 95, details + [f"✅ CS is above target for {position} role. Great farming!"]
    elif cs_per_min >= target * 0.8:
        return "warning", 60, details + [
            f"⚠️ CS is below target ({cs_per_min:.1f} vs {target}).",
            "Try to improve last-hitting consistency. Use practice tool for 10 min/day.",
        ]
    else:
        return "poor", 30, details + [
            f"🔴 CS is significantly below target ({cs_per_min:.1f} vs {target}).",
            "Focus on last-hitting fundamentals. Avoid unnecessary roaming during waves.",
        ]


def _analyze_kp(k: int, d: int, a: int, position: str, benches: dict) -> tuple[str, int, list[str]]:
    details = [f"K/D/A: {k}/{d}/{a}"]
    kda = (k + a) / max(d, 1)
    target_kp = benches["kp_target"]

    # Estimate KP — without team kills, we grade on KDA and deaths
    if kda >= 4.0:
        return "ok", 90, details + [
            f"✅ Excellent KDA ({kda:.1f}). High impact with low deaths.",
        ]
    elif kda >= 2.5:
        return "ok", 75, details + [
            f"✅ Good KDA ({kda:.1f}). Solid performance.",
        ]
    elif kda >= 1.5:
        return "warning", 55, details + [
            f"⚠️ KDA is average ({kda:.1f}).",
            "Look for more opportunities to assist in fights. As support, focus on peeling and enabling your carries.",
        ]
    else:
        return "poor", 30, details + [
            f"🔴 Low KDA ({kda:.1f}).",
            "High deaths relative to kills/assists. Focus on positioning and choosing fights carefully.",
            f"As {position}, aim for kill participation above {target_kp}%.",
        ]


def _analyze_vision(vision_per_min: float, control_wards: int, position: str, benches: dict) -> tuple[str, int, list[str]]:
    target = benches["vision_per_min"]
    cw_target = benches["control_wards_per_game"]
    details = [
        f"Vision score/min: {vision_per_min:.1f} (target: {target})",
        f"Control wards: {control_wards} (target: {cw_target})",
    ]

    # Heavily weight vision for support
    if position == "UTILITY":
        if vision_per_min >= target * 1.2 and control_wards >= cw_target:
            return "ok", 95, details + ["✅ Excellent vision control. Your team has great map awareness."]
        elif vision_per_min >= target * 0.8:
            return "warning", 65, details + [
                "⚠️ Vision score is slightly below expectations for support.",
                "Prioritize warding key objectives (Dragon/Herald) 1 minute before spawn.",
                f"Try to place at least {cw_target} control wards per game.",
            ]
        else:
            return "poor", 35, details + [
                "🔴 Low vision score — your team is playing blind.",
                "Buy control wards on every back. Ward river and enemy jungle entrances.",
                "Complete your support item quest ASAP for unlimited wards.",
            ]
    else:
        # Non-support gets more lenient vision grading
        if vision_per_min >= target:
            return "ok", 85, details + [f"✅ Good vision for {position}."]
        elif vision_per_min >= target * 0.5:
            return "warning", 60, details + [f"⚠️ Below average vision for {position}."]
        else:
            return "poor", 40, details + ["🔴 Very low vision contribution. Buy control wards."]


def _analyze_deaths(d: int, game_minutes: float, position: str, benches: dict) -> tuple[str, int, list[str]]:
    target = benches["deaths_per_game_target"]
    details = [f"Deaths: {d} in {game_minutes:.0f} min (target ≤ {target})"]

    if d <= target * 0.5:
        return "ok", 95, details + ["✅ Very low deaths — excellent survival."]
    elif d <= target:
        return "ok", 80, details + ["✅ Deaths within acceptable range."]
    elif d <= target * 1.5:
        return "warning", 55, details + [
            "⚠️ Death count is higher than ideal.",
            "Review deaths — are you dying to ganks? Poor positioning? Face-checking?",
            "Try to track the enemy jungler and respect missing laners.",
        ]
    else:
        return "poor", 25, details + [
            "🔴 Too many deaths! Each death gives the enemy gold and map pressure.",
            "Focus on playing safer in lane and warding before pushing.",
            "After 2 deaths in lane, switch to playing defensively under tower.",
        ]


def _analyze_items(items: list[int], position: str, match_row: dict) -> tuple[str, int, list[str]]:
    details = []

    # Check if the player bought items at all
    non_zero = [i for i in items if i != 0]
    if len(non_zero) <= 1:
        return "warning", 50, details + ["⚠️ Very few items purchased — check if game was a remake."]

    # Check for control wards in inventory (item ID 2055)
    has_control_ward = 2055 in items
    if position == "UTILITY" and not has_control_ward:
        details.append("⚠️ No control ward in final build — supports should always carry one.")
        score_penalty = 15
    elif not has_control_ward:
        details.append("💡 Consider carrying a control ward for objective vision.")
        score_penalty = 5
    else:
        details.append("✅ Good — had a control ward in inventory.")
        score_penalty = 0

    # Check if trinket was upgraded (item6)
    # 3340 = Stealth Ward (yellow trinket, un-upgraded)
    # 3363 = Farsight Alteration
    # 3364 = Oracle Lens
    trinket = items[6] if len(items) > 6 else 0
    if trinket == 3364 and position == "UTILITY":  # Oracle Lens
        details.append("✅ Oracle Lens — good for support vision denial.")
    elif trinket == 3363:  # Farsight Alteration
        details.append("✅ Farsight — safe warding option.")
    elif trinket == 3340 and position == "UTILITY":
        details.append("⚠️ Still using the basic Stealth Ward (yellow trinket). "
                       "Consider upgrading to Oracle Lens (3364) for vision denial or "
                       "Farsight (3363) for safe scouting once you hit level 9.")

    final_score = max(10, 85 - score_penalty)

    if len(details) <= 1:
        details.append("Item build analysis limited — full item path not available from match summary.")

    return "ok", final_score, details


def _generate_summary(grade: str, score: float, focus_areas: list[str], win: bool) -> str:
    result = "Victory" if win else "Defeat"
    if grade == "S":
        return f"{result} — Outstanding performance (Grade S, {score:.0f}/100). Keep doing what you're doing!"
    elif grade == "A":
        return f"{result} — Strong performance (Grade A, {score:.0f}/100). Minor improvements could push you higher."
    elif grade == "B":
        return f"{result} — Solid game (Grade B, {score:.0f}/100). Focus on: {'; '.join(focus_areas[:2])}."
    elif grade == "C":
        return f"{result} — Below average (Grade C, {score:.0f}/100). Key areas to work on: {'; '.join(focus_areas[:2])}."
    else:
        return f"{result} — Rough game (Grade D, {score:.0f}/100). Don't tilt — focus on: {'; '.join(focus_areas[:2])}."


def compute_trends(matches: list[dict]) -> dict:
    """
    Compute aggregate trends from a list of match dicts.

    Args:
        matches: List of dicts with match data (from SQLite rows).

    Returns:
        Dict with trend metrics.
    """
    if not matches:
        return {
            "matches_analyzed": 0,
            "avg_kda": 0.0,
            "avg_cs_per_min": 0.0,
            "avg_vision_score": 0.0,
            "avg_kill_participation": 0.0,
            "win_rate": 0.0,
            "trend_direction": "stable",
        }

    wins = 0
    total_kda = 0.0
    total_cs = 0.0
    total_vision = 0.0
    count = len(matches)

    for m in matches:
        if m.get("win"):
            wins += 1
        k = m.get("kills", 0)
        d = m.get("deaths", 1)
        a = m.get("assists", 0)
        total_kda += (k + a) / max(d, 1)
        mins = max(m.get("game_duration", 0) / 60, 1)
        cs = m.get("total_minions_killed", 0) + m.get("neutral_minions_killed", 0)
        total_cs += cs / mins
        total_vision += m.get("vision_score", 0)

    avg_kda = total_kda / count
    avg_cs = total_cs / count
    avg_vision = total_vision / count
    win_rate = (wins / count) * 100

    # Simple trend direction based on last 10 vs previous 10
    trend = "stable"
    if count >= 10:
        recent_wins = sum(1 for m in matches[:5] if m.get("win"))
        older_wins = sum(1 for m in matches[5:10] if m.get("win"))
        if recent_wins > older_wins + 1:
            trend = "improving"
        elif older_wins > recent_wins + 1:
            trend = "declining"

    return {
        "matches_analyzed": count,
        "avg_kda": round(avg_kda, 2),
        "avg_cs_per_min": round(avg_cs, 1),
        "avg_vision_score": round(avg_vision, 1),
        "avg_kill_participation": 0.0,  # Needs team data
        "win_rate": round(win_rate, 1),
        "trend_direction": trend,
    }
