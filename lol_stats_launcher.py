"""
LoL Stats — Single-Process Launcher
=====================================
Runs the FastAPI backend and PySide6 overlay in one process.
Used by PyInstaller to create a single EXE.

- Backend (uvicorn) runs in a daemon thread with its own asyncio loop
- Overlay (PySide6) runs in the main thread with Qt's event loop
"""

import asyncio
import logging
import signal
import sys
import threading
from pathlib import Path

# ── Logging ────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("lol_stats")

# Ensure we can find our modules regardless of how we're launched
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def run_backend():
    """Run the FastAPI backend in a background daemon thread."""
    import uvicorn
    from backend.config import load_config

    config = load_config()

    class _ServerThread(threading.Thread):
        def __init__(self):
            super().__init__(name="backend-server", daemon=True)
            self._server = uvicorn.Server(
                uvicorn.Config(
                    "backend.main:create_app",
                    host=config.host,
                    port=config.port,
                    factory=True,
                    log_level="info",
                )
            )

        def run(self):
            self._server.run()

        def stop(self):
            self._server.should_exit = True

    thread = _ServerThread()
    thread.start()
    logger.info("Backend started on http://%s:%d", config.host, config.port)

    # Auto-open browser after a short delay
    import webbrowser
    import time as _time
    def _open_browser():
        _time.sleep(1.5)
        webbrowser.open(f"http://{config.host}:{config.port}")
    threading.Thread(target=_open_browser, daemon=True).start()

    return thread


def run_overlay():
    """Run the PySide6 overlay in the main thread."""
    from overlay.main import LeagueOverlayApp

    app = LeagueOverlayApp()
    return app.run()


def _free_port(port: int):
    """Kill any process already bound to the given port."""
    import subprocess as _sp
    try:
        result = _sp.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = int(parts[-1])
                try:
                    import os as _os
                    _os.kill(pid, 9)
                    logger.info("Killed process PID %d on port %d.", pid, port)
                except Exception:
                    pass
    except Exception:
        pass  # netstat failed — just try binding normally


def main():
    _free_port(8000)

    logger.info("=" * 50)
    logger.info("  LoL Stats — Starting...")
    logger.info("  Web Dashboard: http://localhost:8000")
    logger.info("  Overlay: waiting for game...")
    logger.info("=" * 50)

    # Start backend in background thread
    backend_thread = run_backend()

    # Run overlay in main thread (Qt event loop blocks here)
    exit_code = run_overlay()

    # Cleanup
    logger.info("Shutting down backend...")
    backend_thread.stop()

    logger.info("LoL Stats exited.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
