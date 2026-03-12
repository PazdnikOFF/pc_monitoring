"""
Entry point for pc_monitoring server.

1. Reads / initialises server_config.json (generates pc_id if empty, fills pc_name from hostname).
2. Creates QApplication.
3. Launches MainWindow.
4. Blocks on app.exec().
"""

from __future__ import annotations

import json
import logging
import socket
import sys
import uuid
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from PyQt6.QtWidgets import QApplication

_CONFIG_PATH = Path(__file__).parent / "data" / "server_config.json"

_DEFAULT_CONFIG = {
    "pc_id": "",
    "pc_name": "",
    "port": 8080,
    "ws_port": 8080,
    "refresh_ms": 1000,
    "udp_beacon_port": 45454,
}


def _load_or_create_config() -> dict:
    """Load config from disk, initialise missing fields, write back."""
    config = dict(_DEFAULT_CONFIG)

    if _CONFIG_PATH.exists():
        try:
            on_disk = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            config.update(on_disk)
        except (json.JSONDecodeError, OSError) as exc:
            logging.warning("Could not read server_config.json: %s", exc)

    changed = False

    if not config.get("pc_id"):
        config["pc_id"] = str(uuid.uuid4())
        changed = True
        logging.info("Generated new pc_id: %s", config["pc_id"])

    if not config.get("pc_name"):
        try:
            config["pc_name"] = socket.gethostname()
        except OSError:
            config["pc_name"] = "PC"
        changed = True
        logging.info("Set pc_name: %s", config["pc_name"])

    if changed:
        try:
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CONFIG_PATH.write_text(
                json.dumps(config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logging.error("Failed to save server_config.json: %s", exc)

    return config


def main() -> None:
    config = _load_or_create_config()

    app = QApplication(sys.argv)
    app.setApplicationName("PC Monitoring Server")
    app.setOrganizationName("PCMonitor")
    app.setQuitOnLastWindowClosed(True)

    # Import here so PyQt6 is already initialised
    from server.gui.main_window import MainWindow

    window = MainWindow(config)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
