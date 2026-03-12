"""
Centralized path resolution for script and frozen (PyInstaller) contexts.

When running as a PyInstaller --onefile EXE, __file__ points to a temporary
_MEIPASS directory that is deleted on exit — not suitable for writable data.
Instead, writable data is stored next to the EXE (sys.executable).
"""

from __future__ import annotations

import sys
from pathlib import Path


def _data_root() -> Path:
    if getattr(sys, "frozen", False):
        # Frozen EXE: store data next to the .exe file
        return Path(sys.executable).parent / "data"
    # Script mode: data/ lives inside the server/ package directory
    return Path(__file__).parent / "data"


DATA_DIR: Path = _data_root()
CONFIG_PATH: Path = DATA_DIR / "server_config.json"
DEVICES_JSON: Path = DATA_DIR / "devices.json"
TEMPLATES_DIR: Path = DATA_DIR / "templates"
