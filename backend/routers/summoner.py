"""
LoL Stats - Summoner Router
============================
Endpoints for looking up and managing summoners.
"""

import logging
from fastapi import APIRouter, HTTPException, Request
from backend.models.schemas import SummonerResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/summoner", tags=["summoner"])


def _get_services(request: Request):
    """Get backend services from app state."""
    return request.app.state


@router.get("/{region}/{game_name}/{tag_line}", response_model=SummonerResponse)
async def lookup_summoner(region: str, game_name: str, tag_line: str, request: Request):
    """
    Look up a summoner by Riot ID (game_name#tag_line).
    Fetches from Riot API if not in database, then stores the result.
    """
    state = _get_services(request)
    riot_client = state.riot_client
    db = state.db

    if not riot_client.has_key:
        raise HTTPException(status_code=503, detail="Riot API key not configured. Set RIOT_API_KEY.")

    # Check if we have a cached puuid for this name in DB
    # (We need to search by name which we don't have indexed, so just go via Riot API)
    puuid = riot_client.get_puuid(game_name, tag_line, region)
    if not puuid:
        raise HTTPException(
            status_code=404,
            detail=f"Summoner '{game_name}#{tag_line}' not found in region {region.upper()}.",
        )

    # Get summoner profile from Riot API
    summoner_data = riot_client.get_summoner(puuid, region)
    if not summoner_data:
        raise HTTPException(status_code=502, detail="Failed to fetch summoner profile from Riot API.")

    # Store in database
    db.upsert_summoner(
        puuid=puuid,
        game_name=game_name,
        tag_line=tag_line,
        region=region.lower(),
        profile_icon_id=summoner_data.get("profileIconId", 0),
        summoner_level=summoner_data.get("summonerLevel", 0),
    )

    match_count = db.get_match_count(puuid)

    logger.info("Summoner looked up: %s#%s (%s)", game_name, tag_line, puuid[:8])

    return SummonerResponse(
        puuid=puuid,
        game_name=game_name,
        tag_line=tag_line,
        region=region.lower(),
        profile_icon_id=summoner_data.get("profileIconId", 0),
        summoner_level=summoner_data.get("summonerLevel", 0),
        last_updated="now",
        is_tracked=True,
        match_count=match_count,
    )


@router.get("/{puuid}", response_model=SummonerResponse)
async def get_cached_summoner(puuid: str, request: Request):
    """Get a summoner from the database by PUUID."""
    state = _get_services(request)
    db = state.db

    row = db.fetch_one("SELECT * FROM summoners WHERE puuid = ?", (puuid,))
    if not row:
        raise HTTPException(status_code=404, detail="Summoner not found. Look them up first.")

    match_count = db.get_match_count(puuid)

    return SummonerResponse(
        puuid=row["puuid"],
        game_name=row["game_name"],
        tag_line=row["tag_line"],
        region=row["region"],
        profile_icon_id=row["profile_icon_id"],
        summoner_level=row["summoner_level"],
        last_updated=row["last_updated"],
        is_tracked=bool(row["is_tracked"]),
        match_count=match_count,
    )


@router.delete("/{puuid}")
async def delete_summoner(puuid: str, request: Request):
    """Remove a summoner and all their matches from the database."""
    state = _get_services(request)
    db = state.db

    if not db.summoner_exists(puuid):
        raise HTTPException(status_code=404, detail="Summoner not found.")

    db.execute("DELETE FROM matches WHERE puuid = ?", (puuid,))
    db.execute("DELETE FROM summoners WHERE puuid = ?", (puuid,))

    logger.info("Summoner deleted: %s", puuid[:8])
    return {"message": "Summoner and all matches deleted.", "puuid": puuid}
