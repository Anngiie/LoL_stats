"""
LoL Stats - Matches Router
===========================
Endpoints for fetching and listing match history.
"""

import json
import logging
import sqlite3
from fastapi import APIRouter, HTTPException, Query, Request
from backend.models.schemas import MatchSummary, MatchDetail, MatchListResponse, RefreshResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/matches", tags=["matches"])


def _get_services(request: Request):
    return request.app.state


def _parse_participant(match_data: dict, puuid: str) -> dict | None:
    """
    Extract the tracked summoner's participant data from a full match response.

    The Riot API returns a 'info.participants' list with all 10 players.
    We need to find the one matching our puuid and flatten the relevant fields.
    """
    info = match_data.get("info", {})
    participants = info.get("participants", [])

    for p in participants:
        if p.get("puuid") == puuid:
            # Build a flat dict matching our DB schema
            # Summoner spell IDs are in summoner1Id/summoner2Id
            challenges = p.get("challenges", {})

            return {
                "match_id": match_data.get("metadata", {}).get("matchId", ""),
                "puuid": puuid,
                "game_creation": info.get("gameCreation", 0),
                "game_duration": info.get("gameDuration", 0),
                "game_version": info.get("gameVersion", ""),
                "queue_id": info.get("queueId", 0),
                "platform_id": match_data.get("metadata", {}).get("platformId", ""),
                "champion_id": p.get("championId", 0),
                "champion_name": p.get("championName", ""),
                "individual_position": p.get("individualPosition", ""),
                "team_id": p.get("teamId", 0),
                "win": 1 if p.get("win", False) else 0,
                "kills": p.get("kills", 0),
                "deaths": p.get("deaths", 0),
                "assists": p.get("assists", 0),
                "total_damage_dealt_to_champions": p.get("totalDamageDealtToChampions", 0),
                "total_damage_taken": p.get("totalDamageTaken", 0),
                "gold_earned": p.get("goldEarned", 0),
                "total_minions_killed": p.get("totalMinionsKilled", 0),
                "neutral_minions_killed": p.get("neutralMinionsKilled", 0),
                "vision_score": p.get("visionScore", 0),
                "vision_wards_bought": p.get("visionWardsBoughtInGame", 0),
                "wards_placed": p.get("wardsPlaced", 0),
                "wards_killed": p.get("wardsKilled", 0),
                "control_wards_placed": challenges.get("controlWardsPlaced", 0),
                "item0": p.get("item0", 0),
                "item1": p.get("item1", 0),
                "item2": p.get("item2", 0),
                "item3": p.get("item3", 0),
                "item4": p.get("item4", 0),
                "item5": p.get("item5", 0),
                "item6": p.get("item6", 0),
                "summoner1_id": p.get("summoner1Id", 0),
                "summoner2_id": p.get("summoner2Id", 0),
                "perk_primary_style": p.get("perks", {}).get("styles", [{}])[0].get("style", 0) if p.get("perks", {}).get("styles") else 0,
                "perk_sub_style": p.get("perks", {}).get("styles", [{}, {}])[1].get("style", 0) if len(p.get("perks", {}).get("styles", [])) > 1 else 0,
                "champ_level": p.get("champLevel", 0),
                "champ_experience": p.get("champExperience", 0),
                "double_kills": p.get("doubleKills", 0),
                "triple_kills": p.get("tripleKills", 0),
                "quadra_kills": p.get("quadraKills", 0),
                "penta_kills": p.get("pentaKills", 0),
                "turret_kills": p.get("turretKills", 0),
                "inhibitor_kills": p.get("inhibitorKills", 0),
                "dragon_kills": p.get("dragonKills", 0),
                "baron_kills": p.get("baronKills", 0),
            }

    return None


def _row_to_summary(row: sqlite3.Row) -> MatchSummary:
    return MatchSummary(
        match_id=row["match_id"],
        champion_name=row["champion_name"],
        champion_id=row["champion_id"],
        win=bool(row["win"]),
        kills=row["kills"],
        deaths=row["deaths"],
        assists=row["assists"],
        total_minions_killed=row["total_minions_killed"],
        vision_score=row["vision_score"],
        gold_earned=row["gold_earned"],
        game_duration=row["game_duration"],
        game_creation=row["game_creation"],
        individual_position=row["individual_position"],
        queue_id=row["queue_id"],
        has_analysis=bool(row["analysis_data"]),
    )


def _row_to_detail(row: sqlite3.Row) -> MatchDetail:
    analysis = None
    if row["analysis_data"]:
        try:
            analysis = json.loads(row["analysis_data"])
        except json.JSONDecodeError:
            pass

    return MatchDetail(
        match_id=row["match_id"],
        puuid=row["puuid"],
        game_creation=row["game_creation"],
        game_duration=row["game_duration"],
        game_version=row["game_version"],
        queue_id=row["queue_id"],
        platform_id=row["platform_id"],
        champion_id=row["champion_id"],
        champion_name=row["champion_name"],
        individual_position=row["individual_position"],
        team_id=row["team_id"],
        win=bool(row["win"]),
        kills=row["kills"],
        deaths=row["deaths"],
        assists=row["assists"],
        total_damage_dealt_to_champions=row["total_damage_dealt_to_champions"],
        total_damage_taken=row["total_damage_taken"],
        gold_earned=row["gold_earned"],
        total_minions_killed=row["total_minions_killed"],
        neutral_minions_killed=row["neutral_minions_killed"],
        vision_score=row["vision_score"],
        vision_wards_bought=row["vision_wards_bought"],
        wards_placed=row["wards_placed"],
        wards_killed=row["wards_killed"],
        control_wards_placed=row["control_wards_placed"],
        items=[row[f"item{i}"] for i in range(7)],
        summoner1_id=row["summoner1_id"],
        summoner2_id=row["summoner2_id"],
        perk_primary_style=row["perk_primary_style"],
        perk_sub_style=row["perk_sub_style"],
        champ_level=row["champ_level"],
        double_kills=row["double_kills"] or 0,
        triple_kills=row["triple_kills"] or 0,
        quadra_kills=row["quadra_kills"] or 0,
        penta_kills=row["penta_kills"] or 0,
        turret_kills=row["turret_kills"] or 0,
        inhibitor_kills=row["inhibitor_kills"] or 0,
        dragon_kills=row["dragon_kills"] or 0,
        baron_kills=row["baron_kills"] or 0,
        analysis_data=analysis,
        fetched_at=row["fetched_at"],
    )


@router.get("/{puuid}", response_model=MatchListResponse)
async def list_matches(
    puuid: str,
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    queue: int | None = Query(None, description="Queue filter: 420=ranked solo, 440=flex, 450=ARAM"),
):
    """Get paginated match history for a summoner from the database."""
    state = _get_services(request)
    db = state.db

    if not db.summoner_exists(puuid):
        raise HTTPException(status_code=404, detail="Summoner not found. Look them up first.")

    offset = (page - 1) * per_page

    if queue is not None:
        total = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM matches WHERE puuid = ? AND queue_id = ?",
            (puuid, queue),
        )["cnt"]
        rows = db.fetch_all(
            """SELECT * FROM matches WHERE puuid = ? AND queue_id = ?
               ORDER BY game_creation DESC LIMIT ? OFFSET ?""",
            (puuid, queue, per_page, offset),
        )
    else:
        total = db.get_match_count(puuid)
        rows = db.fetch_all(
            """SELECT * FROM matches WHERE puuid = ?
               ORDER BY game_creation DESC LIMIT ? OFFSET ?""",
            (puuid, per_page, offset),
        )

    matches = [_row_to_summary(r) for r in rows]
    has_more = offset + per_page < total

    return MatchListResponse(
        matches=matches,
        total=total,
        page=page,
        per_page=per_page,
        has_more=has_more,
    )


@router.post("/{puuid}/refresh", response_model=RefreshResponse)
async def refresh_matches(
    puuid: str,
    request: Request,
    count: int = Query(20, ge=1, le=100),
    queue: int | None = Query(None, description="Queue filter: 420=ranked solo, 440=flex, 450=ARAM"),
):
    """
    Fetch new matches from the Riot API and store them.

    Only fetches matches we don't already have in the database.
    """
    state = _get_services(request)
    riot_client = state.riot_client
    db = state.db
    config = state.config

    if not riot_client.has_key:
        raise HTTPException(status_code=503, detail="Riot API key not configured.")

    # Get region from summoner record
    summoner = db.fetch_one("SELECT region FROM summoners WHERE puuid = ?", (puuid,))
    if not summoner:
        raise HTTPException(status_code=404, detail="Summoner not found. Look them up first.")
    region = summoner["region"]

    # Fetch match IDs from Riot
    match_ids = riot_client.get_match_ids(puuid, region, count=count, queue=queue)
    if not match_ids:
        return RefreshResponse(
            puuid=puuid,
            new_matches=0,
            total_matches=db.get_match_count(puuid),
            message="No new matches found on Riot servers.",
        )

    new_count = 0
    for match_id in match_ids:
        if db.match_exists(match_id):
            continue

        # Fetch full match detail
        match_data = riot_client.get_match(match_id, region)
        if not match_data:
            logger.warning("Failed to fetch match %s, skipping.", match_id)
            continue

        participant = _parse_participant(match_data, puuid)
        if not participant:
            logger.warning("Participant not found in match %s, skipping.", match_id)
            continue

        db.insert_match(participant)
        new_count += 1
        logger.debug("Stored match %s (%s)", match_id, participant.get("champion_name", "?"))

    total = db.get_match_count(puuid)
    logger.info("Refresh complete for %s: %d new matches, %d total", puuid[:8], new_count, total)

    return RefreshResponse(
        puuid=puuid,
        new_matches=new_count,
        total_matches=total,
        message=f"Fetched {new_count} new matches. Total: {total}.",
    )


@router.get("/{puuid}/detail/{match_id}", response_model=MatchDetail)
async def get_match_detail(puuid: str, match_id: str, request: Request):
    """Get full detail for a single match."""
    state = _get_services(request)
    db = state.db

    row = db.fetch_one("SELECT * FROM matches WHERE match_id = ? AND puuid = ?", (match_id, puuid))
    if not row:
        raise HTTPException(status_code=404, detail="Match not found.")

    return _row_to_detail(row)
