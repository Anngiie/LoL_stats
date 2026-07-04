#!/usr/bin/env python
"""
LoL Stats — Launcher Script
=============================
Launches both the FastAPI backend and the PySide6 overlay.

Usage:
    python scripts/run.py              # Launch both
    python scripts/run.py --backend    # Backend only
    python scripts/run.py --overlay    # Overlay only
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

_log_level = logging.DEBUG if os.environ.get("LOGGER") == "1" else logging.WARNING
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("launcher")


def run_backend() -> subprocess.Popen:
    """Start the FastAPI backend server."""
    logger.info("Starting backend server...")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:create_app",
         "--host", "127.0.0.1", "--port", "8000", "--factory", "--reload"],
        cwd=str(PROJECT_ROOT),
    )


def run_overlay() -> subprocess.Popen:
    """Start the PySide6 overlay."""
    logger.info("Starting overlay...")
    return subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "overlay" / "main.py")],
        cwd=str(PROJECT_ROOT),
    )


def _free_port(port: int) -> None:
    """Kill whatever is squatting on this port so we can bind."""
    import subprocess as _sp
    try:
        result = _sp.run(["netstat", "-ano"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = int(line.split()[-1])
                try:
                    import os as _os
                    _os.kill(pid, 9)
                    logger.info("Killed PID %d on port %d.", pid, port)
                except Exception:
                    pass
    except Exception:
        pass


def main() -> int:
    _free_port(8000)

    parser = argparse.ArgumentParser(description="LoL Stats Launcher")
    parser.add_argument("--backend", action="store_true", help="Run backend only")
    parser.add_argument("--overlay", action="store_true", help="Run overlay only")
    args = parser.parse_args()

    run_all = not args.backend and not args.overlay

    processes = []

    try:
        if run_all or args.backend:
            proc = run_backend()
            processes.append(("Backend", proc))
            time.sleep(2)  # Let backend start before overlay

        if run_all or args.overlay:
            proc = run_overlay()
            processes.append(("Overlay", proc))
            time.sleep(1)

        if not processes:
            logger.warning("Nothing to run. Use --backend, --overlay, or neither for both.")
            return 1

        logger.info("=" * 50)
        logger.info("  LoL Stats is running!")
        if run_all or args.backend:
            logger.info("  Web Dashboard: http://localhost:8000")
        if run_all or args.overlay:
            logger.info("  Overlay: waiting for game...")
        logger.info("  Press Ctrl+C to stop.")
        logger.info("=" * 50)

        # Wait for processes
        for name, proc in processes:
            proc.wait()

    except KeyboardInterrupt:
        logger.info("\nShutting down...")
    finally:
        for name, proc in processes:
            if proc.poll() is None:
                logger.info("Stopping %s...", name)
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

    logger.info("LoL Stats stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
