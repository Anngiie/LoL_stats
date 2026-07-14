"""
LoL Stats - Analysis Router
============================
Endpoints for match analysis and trends.
"""

import json
import logging
from fastapi import APIRouter, HTTPException, Request
from backend.services.match_analyzer import analyze_match, compute_trends

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


def _get_services(request: Request):
    return request.app.state


@router.get("/{match_id}")
async def get_match_analysis(match_id: str, request: Request):
    """Get improvement analysis for a single match."""
    state = _get_services(request)
    db = state.db

    row = db.fetch_one("SELECT * FROM matches WHERE match_id = ?", (match_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Match not found.")

    # Check if analysis is already cached
    if row["analysis_data"]:
        try:
            return json.loads(row["analysis_data"])
        except json.JSONDecodeError:
            pass  # Recompute if cached data is corrupt

    # Convert sqlite3.Row to dict
    match_dict = dict(row)

    # Run analysis
    analysis = analyze_match(match_dict)
    analysis_json = json.dumps(analysis)

    # Cache in DB
    db.update_match_analysis(match_id, analysis_json)

    return analysis


@router.get("/{puuid}/trends")
async def get_trends(puuid: str, request: Request, limit: int = 20):
    """Get aggregate trends over the last N matches."""
    state = _get_services(request)
    db = state.db

    if not db.summoner_exists(puuid):
        raise HTTPException(status_code=404, detail="Summoner not found.")

    rows = db.fetch_all(
        """SELECT win, kills, deaths, assists, game_duration,
                  total_minions_killed, neutral_minions_killed, vision_score
           FROM matches WHERE puuid = ?
           ORDER BY game_creation DESC LIMIT ?""",
        (puuid, limit),
    )

    matches = [dict(r) for r in rows]
    trends = compute_trends(matches)
    trends["puuid"] = puuid

    return trends


@router.get("/{match_id}/timeline")
async def get_match_timeline(match_id: str, request: Request):
    """Get death events from the match timeline for the tracked player.

    Returns a list of death events with timestamp, killer, and position,
    useful for reviewing death patterns.
    """
    state = _get_services(request)
    db = state.db
    riot_client = state.riot_client

    if not riot_client.has_key:
        raise HTTPException(status_code=503, detail="Riot API key not configured.")

    row = db.fetch_one("SELECT * FROM matches WHERE match_id = ?", (match_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Match not found.")

    puuid = row["puuid"]
    summoner = db.fetch_one("SELECT region FROM summoners WHERE puuid = ?", (puuid,))
    if not summoner:
        raise HTTPException(status_code=404, detail="Summoner not found.")
    region = summoner["region"]

    timeline = riot_client.get_match_timeline(match_id, region)
    if not timeline:
        raise HTTPException(status_code=502, detail="Failed to fetch timeline from Riot API.")

    # Map participantId → puuid and championName
    participants = timeline.get("info", {}).get("participants", [])
    pid_to_puuid = {}
    pid_to_champ = {}
    for p in participants:
        pid = p.get("participantId", 0)
        pid_to_puuid[pid] = p.get("puuid", "")
        pid_to_champ[pid] = p.get("championName", "")

    my_pid = None
    for pid, p_uuid in pid_to_puuid.items():
        if p_uuid == puuid:
            my_pid = pid
            break

    if my_pid is None:
        raise HTTPException(status_code=404, detail="Tracked player not found in timeline.")

    # Extract death events (CHAMPION_KILL where victim is our player)
    deaths = []
    for frame in timeline.get("info", {}).get("frames", []):
        for event in frame.get("events", []):
            if event.get("type") != "CHAMPION_KILL":
                continue
            if event.get("victimId") != my_pid:
                continue

            killer_id = event.get("killerId", 0)
            ts = event.get("timestamp", 0)
            pos = event.get("position", {})
            # Detect if it was a solo kill or multi-person kill
            assisting_killers = [
                pid_to_champ.get(a, "?") for a in event.get("assistingParticipantIds", [])
            ]

            deaths.append({
                "timestamp": ts,
                "time_str": f"{ts // 60000}:{(ts // 1000) % 60:02d}",
                "killer": pid_to_champ.get(killer_id, "Unknown"),
                "assists": assisting_killers,
                "position": {"x": pos.get("x", 0), "y": pos.get("y", 0)},
            })

    return {
        "match_id": match_id,
        "champion_name": row["champion_name"],
        "total_deaths": row["deaths"],
        "deaths": deaths,
    }
