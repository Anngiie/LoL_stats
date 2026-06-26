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

    # Get timeline events for richer analysis
    timeline_rows = db.fetch_all(
        "SELECT * FROM timeline_events WHERE match_id = ? ORDER BY timestamp_ms",
        (match_id,),
    )
    timeline = [dict(r) for r in timeline_rows] if timeline_rows else None

    # Run analysis
    analysis = analyze_match(match_dict, timeline)
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
