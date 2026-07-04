"""
LoL Stats - Strategy Router
============================
CRUD endpoints for champion strategy notes.
Also handles Excel import.
"""

import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from backend.models.schemas import (
    StrategyData,
    StrategyUpdateRequest,
    ImportResponse,
    ChampionStrategy,
)
from backend.services.strategy_manager import StrategyManager
from backend.services.excel_importer import import_from_excel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/strategy", tags=["strategy"])


def _get_manager(request: Request) -> StrategyManager:
    """Get or create the StrategyManager from app state."""
    state = request.app.state
    if not hasattr(state, "strategy_manager"):
        state.strategy_manager = StrategyManager(state.config.strategy_file)
    return state.strategy_manager


@router.get("")
async def get_full_strategy(request: Request):
    """Get the complete strategy data (all champions + global prefs)."""
    mgr = _get_manager(request)
    return mgr.load()


@router.get("/{champion_name}")
async def get_champion_strategy(champion_name: str, request: Request):
    """Get strategy for a single champion."""
    mgr = _get_manager(request)
    entry = mgr.get_champion(champion_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No strategy found for '{champion_name}'.")
    return {"champion": champion_name, **entry}


@router.put("/{champion_name}")
async def update_champion_strategy(champion_name: str, updates: StrategyUpdateRequest, request: Request):
    """Create or update a champion's strategy entry."""
    mgr = _get_manager(request)

    # Only include fields that were actually provided
    update_dict = {}
    if updates.vs_support is not None:
        update_dict["vs_support"] = updates.vs_support
    if updates.with_jungler is not None:
        update_dict["with_jungler"] = updates.with_jungler
    if updates.with_adc is not None:
        update_dict["with_adc"] = updates.with_adc
    if updates.personal_notes is not None:
        update_dict["personal_notes"] = updates.personal_notes
    if updates.overlay_priority is not None:
        update_dict["overlay_priority"] = updates.overlay_priority

    # An empty body is a valid "create with defaults" (the Add Champion flow).
    entry = mgr.update_champion(champion_name, update_dict)
    return {"champion": champion_name, **entry}


@router.delete("/{champion_name}")
async def delete_champion_strategy(champion_name: str, request: Request):
    """Remove a champion's strategy from the database."""
    mgr = _get_manager(request)
    deleted = mgr.delete_champion(champion_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Champion '{champion_name}' not found.")
    return {"message": f"Deleted '{champion_name}'.", "champion": champion_name}


@router.post("/import/excel", response_model=ImportResponse)
async def import_excel(request: Request):
    """
    Import champion strategies from the Coach K Excel spreadsheet.
    Merges with existing data — existing entries are not overwritten.
    """
    mgr = _get_manager(request)

    try:
        result = import_from_excel()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error during Excel import.")
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")

    entries = result["entries"]
    errors = result["errors"]

    if not entries:
        return ImportResponse(
            imported=0,
            skipped=0,
            errors=errors,
            champions=[],
            message=f"No champion data found in Excel file.{' Errors: ' + '; '.join(errors) if errors else ''}",
        )

    # Merge into strategy file
    import_result = mgr.import_champions(entries)

    return ImportResponse(
        imported=import_result["imported"],
        skipped=import_result["skipped"],
        errors=errors,
        champions=import_result["champions"],
        message=(
            f"Imported {import_result['imported']} champions across "
            f"vs-support / with-jungler / with-adc contexts."
            + (f" {len(errors)} warnings." if errors else "")
        ),
    )


@router.post("/global-preferences")
async def update_global_preferences(prefs: dict, request: Request):
    """Update global overlay preferences."""
    mgr = _get_manager(request)
    updated = mgr.update_global_preferences(prefs)
    return updated
