"""
Binding manager — persists device bindings to data/devices.json.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

log = logging.getLogger(__name__)

_DEVICES_JSON = Path(__file__).parent.parent / "data" / "devices.json"


@dataclass
class BoundDevice:
    device_id: str
    mac: str
    display: str
    alias: str = ""
    active_template: str = ""
    last_seen: float = 0.0


class BindingManager:
    """
    Thread-safe manager for bound device records.
    """

    def __init__(self, path: Path = _DEVICES_JSON) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._devices: dict[str, BoundDevice] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_all_devices(self) -> List[BoundDevice]:
        with self._lock:
            return list(self._devices.values())

    def get_device(self, device_id: str) -> Optional[BoundDevice]:
        with self._lock:
            return self._devices.get(device_id)

    def bind(
        self,
        device_id: str,
        mac: str,
        display: str,
        alias: str = "",
    ) -> BoundDevice:
        with self._lock:
            existing = self._devices.get(device_id)
            if existing:
                existing.mac = mac
                existing.display = display
                if alias:
                    existing.alias = alias
                existing.last_seen = time.time()
                dev = existing
            else:
                dev = BoundDevice(
                    device_id=device_id,
                    mac=mac,
                    display=display,
                    alias=alias,
                    last_seen=time.time(),
                )
                self._devices[device_id] = dev
            self._save_locked()
        log.info("Bound device %s (mac=%s)", device_id, mac)
        return dev

    def unbind(self, device_id: str) -> None:
        with self._lock:
            if device_id in self._devices:
                del self._devices[device_id]
                self._save_locked()
                log.info("Unbound device %s", device_id)

    def update_last_seen(self, device_id: str) -> None:
        with self._lock:
            dev = self._devices.get(device_id)
            if dev:
                dev.last_seen = time.time()
                self._save_locked()

    def set_template(self, device_id: str, template_name: str) -> None:
        with self._lock:
            dev = self._devices.get(device_id)
            if dev:
                dev.active_template = template_name
                self._save_locked()

    def set_alias(self, device_id: str, alias: str) -> None:
        with self._lock:
            dev = self._devices.get(device_id)
            if dev:
                dev.alias = alias
                self._save_locked()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            text = self._path.read_text(encoding="utf-8")
            data = json.loads(text)
            for d in data.get("devices", []):
                dev = BoundDevice(
                    device_id=d.get("device_id", ""),
                    mac=d.get("mac", ""),
                    display=d.get("display", ""),
                    alias=d.get("alias", ""),
                    active_template=d.get("active_template", ""),
                    last_seen=d.get("last_seen", 0.0),
                )
                self._devices[dev.device_id] = dev
        except FileNotFoundError:
            log.info("devices.json not found, starting empty")
        except (json.JSONDecodeError, KeyError) as exc:
            log.warning("Failed to load devices.json: %s", exc)

    def _save_locked(self) -> None:
        """Must be called while holding self._lock."""
        try:
            payload = {
                "devices": [asdict(d) for d in self._devices.values()]
            }
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            log.error("Failed to save devices.json: %s", exc)
