"""
LoL Stats - Champions Router
=============================
Static champion data from DataDragon cache.
"""

import logging
import time
from fastapi import APIRouter, HTTPException
from backend.services.riot_client import get_champion_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/champions", tags=["champions"])

# In-memory cache with TTL so it refreshes after a game patch.
_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours
_champion_cache: dict | None = None
_champion_cache_time: float = 0.0


def _load_cache() -> dict:
    """Load champion data from DataDragon, with an expiring in-memory cache."""
    global _champion_cache, _champion_cache_time
    now = time.monotonic()
    if _champion_cache is None or (now - _champion_cache_time) > _CACHE_TTL_SECONDS:
        data = get_champion_data()
        if data:
            # Simplify: extract just the name → id mapping
            cache = {}
            for name, info in data.get("data", {}).items():
                # DataDragon: info["id"] is the string key (e.g. "Aatrox"),
                # info["key"] is the numeric ID as a string (e.g. "266")
                cache[name] = {
                    "id": int(info["key"]),
                    "name": info["name"],
                    "title": info.get("title", ""),
                    "key": info["id"],
                    "version": data.get("version", ""),
                }
            _champion_cache = cache
            _champion_cache_time = now
    return _champion_cache or {}


@router.get("")
async def list_champions():
    """Get all champion names and IDs."""
    cache = _load_cache()
    if not cache:
        raise HTTPException(status_code=502, detail="Failed to load champion data from DataDragon.")

    # Return as list sorted by name
    return [
        {"name": name, "id": info["id"], "title": info["title"], "key": info["key"]}
        for name, info in sorted(cache.items())
    ]


@router.get("/version")
async def get_version():
    """Get the current DataDragon version used for icon/tile URLs."""
    cache = _load_cache()
    if not cache:
        raise HTTPException(status_code=502, detail="Champion data not loaded.")
    version = next(iter(cache.values())).get("version", "")
    return {"version": version}


@router.get("/{champion_name}")
async def get_champion(champion_name: str):
    """Get info for a single champion by name."""
    cache = _load_cache()
    if not cache:
        raise HTTPException(status_code=502, detail="Failed to load champion data.")

    # Case-insensitive lookup
    for name, info in cache.items():
        if name.lower() == champion_name.lower():
            return info

    raise HTTPException(status_code=404, detail=f"Champion '{champion_name}' not found.")


@router.get("/id/{champion_id}")
async def get_champion_by_id(champion_id: int):
    """Get champion info by numeric ID."""
    cache = _load_cache()
    if not cache:
        raise HTTPException(status_code=502, detail="Failed to load champion data.")

    for name, info in cache.items():
        if info["id"] == champion_id:
            return info

    raise HTTPException(status_code=404, detail=f"Champion ID {champion_id} not found.")
