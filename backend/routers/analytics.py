"""
LoL Stats - Analytics Router
=============================
Aggregate analytics for the home dashboard: performance trends,
coaching insights, champion pool stats, and recent form.

Provides a single endpoint that returns everything the dashboard
charts need in one round-trip.
"""

import logging
from collections import Counter, defaultdict

from fastapi import APIRouter, HTTPException, Query, Request

from backend.services.match_analyzer import BENCHMARKS, _DEFAULT_BENCHMARKS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

# Approximate community-estimated averages for the support role by rank.
# Riot's API doesn't expose per-rank aggregates, so these are reference values.
RANK_BENCHMARKS = {
    "IRON": {
        "kda": 1.8,
        "vision_per_min": 0.6,
        "gold_per_min": 200,
        "dmg_per_min": 280,
    },
    "BRONZE": {
        "kda": 2.0,
        "vision_per_min": 0.8,
        "gold_per_min": 220,
        "dmg_per_min": 310,
    },
    "SILVER": {
        "kda": 2.2,
        "vision_per_min": 1.0,
        "gold_per_min": 235,
        "dmg_per_min": 340,
    },
    "GOLD": {
        "kda": 2.4,
        "vision_per_min": 1.2,
        "gold_per_min": 250,
        "dmg_per_min": 370,
    },
    "PLATINUM": {
        "kda": 2.6,
        "vision_per_min": 1.4,
        "gold_per_min": 260,
        "dmg_per_min": 400,
    },
    "EMERALD": {
        "kda": 2.8,
        "vision_per_min": 1.5,
        "gold_per_min": 270,
        "dmg_per_min": 430,
    },
    "DIAMOND": {
        "kda": 3.0,
        "vision_per_min": 1.6,
        "gold_per_min": 280,
        "dmg_per_min": 460,
    },
    "MASTER": {
        "kda": 3.3,
        "vision_per_min": 1.8,
        "gold_per_min": 290,
        "dmg_per_min": 500,
    },
}


def _get_services(request: Request):
    """Get backend services from app state."""
    return request.app.state


def _determine_primary_role(rows: list[dict]) -> str:
    """Find the most common individual_position across recent matches."""
    positions = [r["individual_position"] for r in rows if r.get("individual_position")]
    if not positions:
        return "UTILITY"
    return Counter(positions).most_common(1)[0][0]


def _build_time_series(rows: list[dict]) -> list[dict]:
    """Build chronological per-game data for charting (oldest first)."""
    series = []
    for r in reversed(rows):
        duration = max(r.get("game_duration", 0), 1)
        cs = r.get("total_minions_killed", 0) + r.get("neutral_minions_killed", 0)
        k = r.get("kills", 0)
        d = r.get("deaths", 0)
        a = r.get("assists", 0)
        vision = r.get("vision_score", 0)
        gold = r.get("gold_earned", 0)
        dmg = r.get("total_damage_dealt_to_champions", 0)

        minutes = duration / 60

        series.append({
            "match_id": r.get("match_id", ""),
            "champion_name": r.get("champion_name", ""),
            "win": bool(r.get("win", 0)),
            "game_creation": r.get("game_creation", 0),
            "queue_id": r.get("queue_id", 0),
            "kda": round((k + a) / max(d, 1), 2),
            "cs_per_min": round(cs / minutes, 1),
            "vision_per_min": round(vision / minutes, 2),
            "gold_per_min": round(gold / minutes, 1),
            "dmg_per_min": round(dmg / minutes, 1),
        })
    return series


def _build_summary(rows: list[dict], role: str) -> dict:
    """Compute aggregate stats from match rows."""
    if not rows:
        return _empty_summary()

    n = len(rows)
    wins = sum(1 for r in rows if r.get("win"))
    losses = n - wins
    win_rate = round((wins / n) * 100) if n else 0

    total_duration = sum(r.get("game_duration", 0) for r in rows)
    total_minutes = max(total_duration / 60, 1)

    avg_kills = sum(r.get("kills", 0) for r in rows) / n
    avg_deaths = sum(r.get("deaths", 0) for r in rows) / n
    avg_assists = sum(r.get("assists", 0) for r in rows) / n
    avg_kda = round((avg_kills + avg_assists) / max(avg_deaths, 1), 2)

    avg_vision = sum(r.get("vision_score", 0) for r in rows) / n
    avg_vision_per_min = round(avg_vision / (total_minutes / n), 2)

    avg_gold = sum(r.get("gold_earned", 0) for r in rows) / n
    avg_gold_per_min = round(avg_gold / (total_minutes / n), 1)

    avg_dmg = sum(r.get("total_damage_dealt_to_champions", 0) for r in rows) / n
    avg_dmg_per_min = round(avg_dmg / (total_minutes / n), 1)

    # Trend: compare KDA of recent half vs older half
    half = max(n // 2, 1)
    recent = rows[:half]
    older = rows[half:] if len(rows) > half else rows

    def avg_kda_of(group):
        k = sum(r.get("kills", 0) for r in group) / max(len(group), 1)
        d = sum(r.get("deaths", 0) for r in group) / max(len(group), 1)
        a = sum(r.get("assists", 0) for r in group) / max(len(group), 1)
        return (k + a) / max(d, 1)

    recent_kda = avg_kda_of(recent)
    older_kda = avg_kda_of(older)

    if recent_kda > older_kda * 1.15:
        trend_direction = "improving"
    elif recent_kda < older_kda * 0.85:
        trend_direction = "declining"
    else:
        trend_direction = "stable"

    return {
        "games": n,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "avg_kda": avg_kda,
        "avg_kills": round(avg_kills, 1),
        "avg_deaths": round(avg_deaths, 1),
        "avg_assists": round(avg_assists, 1),
        "avg_vision_per_min": avg_vision_per_min,
        "avg_gold_per_min": avg_gold_per_min,
        "avg_dmg_per_min": avg_dmg_per_min,
        "trend_direction": trend_direction,
        "role": role,
    }


def _build_champion_stats(rows: list[dict]) -> list[dict]:
    """Aggregate per-champion win rates and game counts."""
    pool = defaultdict(lambda: {"games": 0, "wins": 0})

    for r in rows:
        name = r.get("champion_name", "Unknown")
        pool[name]["games"] += 1
        if r.get("win"):
            pool[name]["wins"] += 1

    stats = []
    for champ, data in pool.items():
        games = data["games"]
        wins = data["wins"]
        losses = games - wins
        win_rate = round((wins / games) * 100) if games else 0
        stats.append({
            "champion": champ,
            "games": games,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
        })

    stats.sort(key=lambda x: x["games"], reverse=True)
    return stats


def _build_coaching(rows: list[dict], role: str) -> list[dict]:
    """
    Generate prioritized coaching advice from aggregate stats.

    Each item: {area, severity, message, metric, target}
    Sorted worst-first so the most impactful advice is at the top.
    """
    if not rows:
        return []

    n = len(rows)
    benches = BENCHMARKS.get(role, _DEFAULT_BENCHMARKS)

    advice = []

    # ── Deaths ──
    avg_deaths = sum(r.get("deaths", 0) for r in rows) / n
    deaths_target = benches.get("deaths_per_game_target", 5)

    if avg_deaths > deaths_target + 1.5:
        advice.append({
            "area": "Deaths",
            "severity": "poor",
            "metric": f"{avg_deaths:.1f} per game",
            "target": f"≤ {deaths_target}",
            "message": (
                f"You're averaging {avg_deaths:.1f} deaths per game — well above the "
                f"{deaths_target} target for {role}. Each death hands the enemy gold and "
                f"map pressure. After 2 deaths in lane, play defensively under tower and "
                f"track the enemy jungler before pushing."
            ),
        })
    elif avg_deaths > deaths_target + 0.5:
        advice.append({
            "area": "Deaths",
            "severity": "warning",
            "metric": f"{avg_deaths:.1f} per game",
            "target": f"≤ {deaths_target}",
            "message": (
                f"Deaths are slightly high ({avg_deaths:.1f} vs {deaths_target} target). "
                f"Review your death timestamps — are they to ganks, face-checking, or "
                f"poor teamfight positioning?"
            ),
        })

    # ── Vision ──
    total_duration = sum(r.get("game_duration", 0) for r in rows)
    total_minutes = max(total_duration / 60, 1)
    avg_vision = sum(r.get("vision_score", 0) for r in rows) / n
    vision_per_min = round(avg_vision / (total_minutes / n), 2)
    vision_target = benches.get("vision_per_min", 1.5)

    if vision_per_min < vision_target * 0.6:
        advice.append({
            "area": "Vision",
            "severity": "poor",
            "metric": f"{vision_per_min}/min",
            "target": f"{vision_target}/min",
            "message": (
                f"Vision score is critically low ({vision_per_min}/min vs {vision_target}/min "
                f"target). Buy control wards on every back, ward objective pits 1 minute "
                f"before spawn, and complete your support item quest early for unlimited wards."
            ),
        })
    elif vision_per_min < vision_target * 0.85:
        advice.append({
            "area": "Vision",
            "severity": "warning",
            "metric": f"{vision_per_min}/min",
            "target": f"{vision_target}/min",
            "message": (
                f"Vision is slightly below target ({vision_per_min}/min). Prioritize deep "
                f"wards in the enemy jungle and river control around objective spawns."
            ),
        })

    # ── KDA ──
    avg_kills = sum(r.get("kills", 0) for r in rows) / n
    avg_assists = sum(r.get("assists", 0) for r in rows) / n
    avg_kda = (avg_kills + avg_assists) / max(avg_deaths, 1)

    if avg_kda < 2.0:
        advice.append({
            "area": "KDA",
            "severity": "poor",
            "metric": f"{avg_kda:.2f}",
            "target": "≥ 2.5",
            "message": (
                f"Your average KDA is {avg_kda:.2f} — high deaths relative to kills+assists. "
                f"Focus on peeling for your carries in fights and look for assist opportunities "
                f"rather than risky engages."
            ),
        })
    elif avg_kda < 2.5:
        advice.append({
            "area": "KDA",
            "severity": "warning",
            "metric": f"{avg_kda:.2f}",
            "target": "≥ 2.5",
            "message": (
                f"Average KDA is {avg_kda:.2f}. Look for more opportunities to assist — "
                f"roam mid when your ADC is safe, and join skirmishes around objectives."
            ),
        })

    # ── Momentum (win rate trend) ──
    half = max(n // 2, 1)
    recent_wr = sum(1 for r in rows[:half] if r.get("win")) / half * 100
    older_wr = sum(1 for r in rows[half:] if r.get("win")) / max(len(rows) - half, 1) * 100

    if recent_wr < older_wr - 15:
        advice.append({
            "area": "Momentum",
            "severity": "warning",
            "metric": f"{recent_wr:.0f}% recent",
            "target": f"{older_wr:.0f}% previous",
            "message": (
                f"Your win rate dropped from {older_wr:.0f}% to {recent_wr:.0f}% in recent games. "
                f"Consider taking a short break, reviewing replays, or sticking to your comfort champions."
            ),
        })
    elif recent_wr > older_wr + 15:
        advice.append({
            "area": "Momentum",
            "severity": "ok",
            "metric": f"{recent_wr:.0f}% recent",
            "target": f"{older_wr:.0f}% previous",
            "message": (
                f"Win rate improved from {older_wr:.0f}% to {recent_wr:.0f}% — you're on the "
                f"right track. Keep up the consistency!"
            ),
        })

    # ── Consistency (fallback) ──
    if not any(a["severity"] == "poor" for a in advice):
        advice.append({
            "area": "Consistency",
            "severity": "ok",
            "metric": f"{n} games",
            "target": "",
            "message": (
                "No critical weaknesses detected in your recent games. Focus on maintaining "
                "consistency and refining your champion mechanics."
            ),
        })

    severity_order = {"poor": 0, "warning": 1, "ok": 2}
    advice.sort(key=lambda a: severity_order.get(a["severity"], 3))

    return advice


def _empty_summary() -> dict:
    return {
        "games": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0,
        "avg_kda": 0,
        "avg_kills": 0,
        "avg_deaths": 0,
        "avg_assists": 0,
        "avg_vision_per_min": 0,
        "avg_gold_per_min": 0,
        "avg_dmg_per_min": 0,
        "trend_direction": "stable",
        "role": "UTILITY",
    }


@router.get("/{puuid}/overview")
async def get_overview(
    puuid: str,
    request: Request,
    limit: int = Query(20, ge=1, le=100),
):
    """
    Get a full analytics overview for the dashboard.

    Returns time-series data for charts, aggregate summary stats,
    champion pool breakdown, auto-generated coaching advice, and
    recent W/L form — all in one response.
    """
    state = _get_services(request)
    db = state.db

    if not db.summoner_exists(puuid):
        raise HTTPException(status_code=404, detail="Summoner not found.")

    rows = db.fetch_all(
        """SELECT match_id, champion_name, win, kills, deaths, assists,
                  game_duration, game_creation, queue_id,
                  total_minions_killed, neutral_minions_killed,
                  vision_score, gold_earned,
                  total_damage_dealt_to_champions, individual_position
           FROM matches WHERE puuid = ?
           ORDER BY game_creation DESC LIMIT ?""",
        (puuid, limit),
    )

    rows = [dict(r) for r in rows]

    if not rows:
        raise HTTPException(status_code=404, detail="No matches found. Refresh to fetch games.")

    role = _determine_primary_role(rows)

    summary = _build_summary(rows, role)
    time_series = _build_time_series(rows)
    champion_stats = _build_champion_stats(rows)
    coaching = _build_coaching(rows, role)
    recent_form = ["W" if r.get("win") else "L" for r in rows]

    return {
        "summary": summary,
        "time_series": time_series,
        "champion_stats": champion_stats,
        "coaching": coaching,
        "recent_form": recent_form,
        "rank_benchmarks": RANK_BENCHMARKS,
    }
