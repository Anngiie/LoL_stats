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
    Also computes team-wide stats (team_kills) and lane context (lane partner).
    """
    info = match_data.get("info", {})
    participants = info.get("participants", [])

    target = None
    for p in participants:
        if p.get("puuid") == puuid:
            target = p
            break

    if not target:
        return None

    challenges = target.get("challenges", {})

    # ── Compute team kills and lane partner from all participants ──
    team_id = target.get("teamId", 0)
    my_position = target.get("individualPosition", "")
    team_kills = sum(
        p.get("kills", 0) for p in participants if p.get("teamId") == team_id
    )

    # Lane partner: the other BOTTOM player on the same team (the ADC,
    # if the tracked player is support, or vice-versa).
    lane_partner_champion = ""
    for p in participants:
        if p.get("puuid") == puuid:
            continue
        if p.get("teamId") != team_id:
            continue
        if p.get("individualPosition") == "BOTTOM" and my_position in ("UTILITY", "BOTTOM"):
            lane_partner_champion = p.get("championName", "")
            break

    return {
        "match_id": match_data.get("metadata", {}).get("matchId", ""),
        "puuid": puuid,
        "game_creation": info.get("gameCreation", 0),
        "game_duration": info.get("gameDuration", 0),
        "game_version": info.get("gameVersion", ""),
        "queue_id": info.get("queueId", 0),
        "platform_id": match_data.get("metadata", {}).get("platformId", ""),
        "champion_id": target.get("championId", 0),
        "champion_name": target.get("championName", ""),
        "individual_position": target.get("individualPosition", ""),
        "team_id": team_id,
        "win": 1 if target.get("win", False) else 0,
        "kills": target.get("kills", 0),
        "deaths": target.get("deaths", 0),
        "assists": target.get("assists", 0),
        "total_damage_dealt_to_champions": target.get("totalDamageDealtToChampions", 0),
        "total_damage_taken": target.get("totalDamageTaken", 0),
        "gold_earned": target.get("goldEarned", 0),
        "total_minions_killed": target.get("totalMinionsKilled", 0),
        "neutral_minions_killed": target.get("neutralMinionsKilled", 0),
        "vision_score": target.get("visionScore", 0),
        "vision_wards_bought": target.get("visionWardsBoughtInGame", 0),
        "wards_placed": target.get("wardsPlaced", 0),
        "wards_killed": target.get("wardsKilled", 0),
        "control_wards_placed": challenges.get("controlWardsPlaced", 0),
        "item0": target.get("item0", 0),
        "item1": target.get("item1", 0),
        "item2": target.get("item2", 0),
        "item3": target.get("item3", 0),
        "item4": target.get("item4", 0),
        "item5": target.get("item5", 0),
        "item6": target.get("item6", 0),
        "summoner1_id": target.get("summoner1Id", 0),
        "summoner2_id": target.get("summoner2Id", 0),
        "perk_primary_style": target.get("perks", {}).get("styles", [{}])[0].get("style", 0) if target.get("perks", {}).get("styles") else 0,
        "perk_sub_style": target.get("perks", {}).get("styles", [{}, {}])[1].get("style", 0) if len(target.get("perks", {}).get("styles", [])) > 1 else 0,
        "champ_level": target.get("champLevel", 0),
        "champ_experience": target.get("champExperience", 0),
        "double_kills": target.get("doubleKills", 0),
        "triple_kills": target.get("tripleKills", 0),
        "quadra_kills": target.get("quadraKills", 0),
        "penta_kills": target.get("pentaKills", 0),
        "turret_kills": target.get("turretKills", 0),
        "inhibitor_kills": target.get("inhibitorKills", 0),
        "dragon_kills": target.get("dragonKills", 0),
        "baron_kills": target.get("baronKills", 0),
        "team_kills": team_kills,
        "lane_partner_champion": lane_partner_champion,
    }


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
        neutral_minions_killed=row["neutral_minions_killed"],
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
        team_kills=row["team_kills"] if "team_kills" in row.keys() else 0,
        lane_partner_champion=row["lane_partner_champion"] if "lane_partner_champion" in row.keys() else "",
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


@router.post("/auto-refresh")
async def auto_refresh_tracked(request: Request):
    """Auto-refresh matches for the tracked summoner.

    Called by the overlay ~60s after a game ends so the dashboard
    is current when the player alt-tabs out. Finds the one tracked
    summoner automatically — no puuid needed.
    """
    state = _get_services(request)
    riot_client = state.riot_client
    db = state.db

    if not riot_client.has_key:
        return {"message": "API key not configured.", "new_matches": 0}

    row = db.fetch_one("SELECT puuid, region FROM summoners WHERE is_tracked = 1 LIMIT 1")
    if not row:
        return {"message": "No tracked summoner.", "new_matches": 0}

    puuid = row["puuid"]
    region = row["region"]

    match_ids = riot_client.get_match_ids(puuid, region, count=5)
    new_count = 0
    for match_id in match_ids:
        if db.match_exists(match_id):
            continue
        match_data = riot_client.get_match(match_id, region)
        if not match_data:
            continue
        participant = _parse_participant(match_data, puuid)
        if not participant:
            continue
        db.insert_match(participant)
        new_count += 1

    logger.info("Auto-refresh: %d new matches for %s", new_count, puuid[:8])
    return {"message": f"Auto-refreshed: {new_count} new matches.", "new_matches": new_count}
