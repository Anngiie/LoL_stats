"""
LoL Stats — PyInstaller Build Script
======================================
Creates a single lol_stats.exe from the project.

Usage:
    python build_exe.py

Requires:
    pip install pyinstaller

The resulting exe will be in dist/lol_stats.exe
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

# Hidden imports that PyInstaller might not auto-detect
HIDDEN_IMPORTS = [
    # FastAPI / Starlette internals
    "fastapi",
    "starlette",
    "uvicorn",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    # WebSockets (for potential future use)
    "websockets",
    "websockets.legacy",
    "websockets.legacy.server",
    # Backend modules
    "backend",
    "backend.main",
    "backend.config",
    "backend.database",
    "backend.routers",
    "backend.routers.summoner",
    "backend.routers.matches",
    "backend.routers.analysis",
    "backend.routers.strategy",
    "backend.routers.champions",
    "backend.services",
    "backend.services.riot_client",
    "backend.services.match_analyzer",
    "backend.services.strategy_manager",
    "backend.services.excel_importer",
    "backend.models",
    "backend.models.schemas",
    # Overlay modules
    "overlay",
    "overlay.main",
    "overlay.league_overlay",
    "overlay.live_client",
    "overlay.game_phase_detector",
    "overlay.strategy_reader",
    # Python stdlib that PyInstaller sometimes misses
    "asyncio",
    "concurrent.futures",
    "email.mime.multipart",
    "email.mime.text",
]

# Data files to bundle (source path -> destination dir inside exe)
DATA_FILES = [
    ("frontend", "frontend"),
    ("shared", "shared"),
    ("backend/data", "backend/data"),
]

# Excluded modules to keep exe size reasonable
EXCLUDES = [
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "PIL",
    "cv2",
    "test",
    "tests",
    "setuptools",
    "pip",
]

def build():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", "lol_stats",
        "--icon", str(PROJECT_ROOT / "LoL_stats icon (2).ico"),
        "--clean",
        "--noconfirm",
    ]

    # Hidden imports
    for imp in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", imp])

    # Excluded modules
    for exc in EXCLUDES:
        cmd.extend(["--exclude-module", exc])

    # Data files
    for src, dest in DATA_FILES:
        full_src = str(PROJECT_ROOT / src)
        if Path(full_src).exists():
            cmd.extend(["--add-data", f"{full_src}{os.pathsep}{dest}"])

    # Exclude the Coach K Excel from the bundle (it's 11 MB)
    cmd.extend(["--add-data", f"{str(PROJECT_ROOT / 'shared' / 'strategy.json')}{os.pathsep}shared"])

    # Bundle the app icon (used for system tray)
    icon_file = PROJECT_ROOT / "LoL_stats icon (2).ico"
    if icon_file.exists():
        cmd.extend(["--add-data", f"{str(icon_file)}{os.pathsep}."])

    # Entry point
    cmd.append(str(PROJECT_ROOT / "lol_stats_launcher.py"))

    print("=" * 60)
    print("  Building LoL Stats EXE...")
    print("=" * 60)
    print("Command:")
    print(" ".join(cmd))
    print()

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode

if __name__ == "__main__":
    sys.exit(build())
