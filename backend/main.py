"""
LoL Stats - FastAPI Application
================================
Main entry point for the backend server.
Serves the REST API and the static frontend files.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.config import load_config, BackendConfig
from backend.database import Database
from backend.services.riot_client import RiotClient

# Configure logging — console output only when LOGGER=1 env var is set
_log_level = logging.DEBUG if os.environ.get("LOGGER") == "1" else logging.WARNING
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("lol_stats")


# ─── Application State ──────────────────────────────────────


class AppState:
    """Shared application state attached to request.app.state."""

    def __init__(self) -> None:
        self.config: BackendConfig = load_config()
        self.db: Database = Database(self.config.database_path)
        self.riot_client: RiotClient = RiotClient(
            api_key=self.config.riot_api_key,
            per_second=self.config.rate_limit_per_second,
            per_2min=self.config.rate_limit_per_2min,
        )


# ─── Lifespan ───────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("=" * 50)
    logger.info("  LoL Stats — Starting Backend")
    logger.info("=" * 50)

    # Initialize
    state = AppState()
    state.db.init_db()

    # Ensure shared directory exists
    shared_dir = Path(state.config.strategy_file).parent
    shared_dir.mkdir(parents=True, exist_ok=True)

    # Create default strategy.json if it doesn't exist
    strategy_file = Path(state.config.strategy_file)
    if not strategy_file.exists():
        import json

        default_strategy = {
            "version": 2,
            "last_updated": "",
            "champions": {},
            "global_preferences": {
                "overlay_auto_show_loading_screen": True,
                "overlay_show_duration_seconds": 15,
                "overlay_opacity": 0.85,
                "overlay_font_size": 14,
                "overlay_font_family": "Segoe UI",
                "overlay_width": 500,
                "overlay_x": 20,
                "overlay_y": 60,
            },
        }
        strategy_file.write_text(json.dumps(default_strategy, indent=2))
        logger.info("Created default strategy.json at %s", strategy_file)

    # Store state on the app for routers to access
    app.state.config = state.config
    app.state.db = state.db
    app.state.riot_client = state.riot_client
    app.state.strategy_file = str(strategy_file)

    logger.info("Backend ready at http://%s:%d", state.config.host, state.config.port)

    if not state.config.riot_api_key:
        logger.warning(
            "No Riot API key configured! Set RIOT_API_KEY env var or "
            "edit backend/data/config.json. Match fetching will not work."
        )

    yield

    # Shutdown
    logger.info("Backend shutting down.")


# ─── App Creation ───────────────────────────────────────────


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="LoL Stats",
        description="League of Legends match history & live game strategy overlay",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — allow local frontend dev on any port
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    from backend.routers import summoner, matches

    app.include_router(summoner.router)
    app.include_router(matches.router)

    # Lazy-import routers for phases that may not be implemented yet
    try:
        from backend.routers import analysis
        app.include_router(analysis.router)
    except (ImportError, AttributeError):
        logger.debug("Analysis router not yet available.")

    try:
        from backend.routers import strategy
        app.include_router(strategy.router)
    except (ImportError, AttributeError):
        logger.debug("Strategy router not yet available.")

    try:
        from backend.routers import champions
        app.include_router(champions.router)
    except (ImportError, AttributeError):
        logger.debug("Champions router not yet available.")

    try:
        from backend.routers import analytics
        app.include_router(analytics.router)
    except (ImportError, AttributeError):
        logger.debug("Analytics router not yet available.")

    # ── Health check endpoint ──

    @app.get("/api/v1/health")
    async def health():
        import os
        from pathlib import Path
        import requests
        import urllib3

        state = app.state

        # Check live client
        live_client_ok = False
        try:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            r = requests.get(
                f"{state.config.live_client_url}/liveclientdata/gamestats",
                timeout=2,
                verify=False,
            )
            live_client_ok = r.status_code == 200
        except Exception:
            pass

        strategy_ok = Path(state.config.strategy_file).exists()

        return {
            "status": "ok",
            "riot_api_key_configured": state.config.riot_api_key != "",
            "database_ok": True,  # Would be False if init failed
            "strategy_file_ok": strategy_ok,
            "live_client_reachable": live_client_ok,
            "version": "0.1.0",
        }

    # ── Static frontend files ──

    frontend_dir = Path(__file__).parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
        logger.info("Mounted frontend from %s", frontend_dir)

    return app


# ─── Entry Point ────────────────────────────────────────────


def main():
    """Launch the backend server."""
    import uvicorn

    config = load_config()
    uvicorn.run(
        "backend.main:create_app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        factory=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
