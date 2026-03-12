"""
Main application window.

- Hosts 4 tabs: Sensors, Templates, Devices, Network
- Runs FastAPI/uvicorn in a background thread with its own event loop
- Runs DiscoveryService in a background thread
- Cleans up all services on close
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Optional

import uvicorn
from fastapi import FastAPI
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QIcon
from PyQt6.QtWidgets import (
    QMainWindow,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QMenu,
    QApplication,
)

from server.api.sensors import router as sensors_router
from server.api.templates import router as templates_router
from server.api.devices import router as devices_router
from server.api.websocket import router as ws_router
from server.core.binding import BindingManager
from server.core.discovery import DiscoveryService
from server.core.mahm_reader import MAHMReader
from server.gui.tab_sensors import TabSensors
from server.gui.tab_templates import TabTemplates
from server.gui.tab_devices import TabDevices
from server.gui.tab_network import TabNetwork

log = logging.getLogger(__name__)

from server.paths import CONFIG_PATH as _CONFIG_PATH


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "pc_id": "",
            "pc_name": "",
            "port": 8080,
            "ws_port": 8080,
            "refresh_ms": 1000,
            "udp_beacon_port": 45454,
        }


def _save_config(config: dict) -> None:
    try:
        _CONFIG_PATH.write_text(
            json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        log.error("Failed to save config: %s", exc)


def _build_app(mahm_reader: MAHMReader, binding: BindingManager,
               discovery: DiscoveryService, config: dict) -> FastAPI:
    app = FastAPI(title="PC Monitoring Server")
    app.include_router(sensors_router)
    app.include_router(templates_router)
    app.include_router(devices_router)
    app.include_router(ws_router)

    app.state.mahm_reader = mahm_reader
    app.state.binding_manager = binding
    app.state.discovery_service = discovery
    app.state.config = config

    return app


class _ServerThread(threading.Thread):
    """Runs uvicorn in an isolated asyncio event loop."""

    def __init__(self, app: FastAPI, host: str, port: int) -> None:
        super().__init__(name="uvicorn-thread", daemon=True)
        self._app = app
        self._host = host
        self._port = port
        self._server: Optional[uvicorn.Server] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        config = uvicorn.Config(
            app=self._app,
            host=self._host,
            port=self._port,
            loop="none",        # we manage the loop ourselves
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        try:
            self._loop.run_until_complete(self._server.serve())
        except Exception as exc:
            log.error("uvicorn error: %s", exc)
        finally:
            self._loop.close()

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True


class MainWindow(QMainWindow):
    def __init__(self, config: dict) -> None:
        super().__init__()
        self._config = config

        self.setWindowTitle(
            f"PC Monitoring — {config.get('pc_name', '')} [{config.get('pc_id', '')}]"
        )
        self.setMinimumSize(800, 600)

        # Core services
        self._mahm = MAHMReader()
        self._binding = BindingManager()
        self._discovery = DiscoveryService(
            udp_port=config.get("udp_beacon_port", 45454)
        )

        # FastAPI app
        self._fastapi_app = _build_app(
            self._mahm, self._binding, self._discovery, config
        )

        # Build GUI
        self._setup_ui()

        # Start background services
        self._discovery.start()
        self._start_server()
        self._setup_tray()

    # ------------------------------------------------------------------
    # GUI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        self._tab_sensors = TabSensors(self._mahm, self)
        self._tab_templates = TabTemplates(self._mahm, self)
        self._tab_devices = TabDevices(self._discovery, self._binding, self._config, self)
        self._tab_network = TabNetwork(
            self._config, on_port_change=self._on_port_change, parent=self
        )

        self._tabs.addTab(self._tab_sensors, "Мониторинг")
        self._tabs.addTab(self._tab_templates, "Шаблоны")
        self._tabs.addTab(self._tab_devices, "Устройства")
        self._tabs.addTab(self._tab_network, "Сеть")

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self._tray = QSystemTrayIcon(self)
        # Use a built-in icon as a placeholder
        self._tray.setIcon(self.style().standardIcon(
            self.style().StandardPixmap.SP_ComputerIcon
        ))
        self._tray.setToolTip("PC Monitoring Server")

        tray_menu = QMenu()
        show_action = tray_menu.addAction("Показать")
        show_action.triggered.connect(self.showNormal)
        quit_action = tray_menu.addAction("Выход")
        quit_action.triggered.connect(QApplication.instance().quit)

        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.activateWindow()

    # ------------------------------------------------------------------
    # Server
    # ------------------------------------------------------------------

    def _start_server(self) -> None:
        port = self._config.get("port", 8080)
        self._server_thread = _ServerThread(self._fastapi_app, "0.0.0.0", port)
        self._server_thread.start()
        log.info("uvicorn started on port %d", port)

    def _on_port_change(self, new_port: int) -> None:
        _save_config(self._config)
        log.info("Port changed to %d — restart required", new_port)

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        log.info("Shutting down...")
        self._tab_sensors.stop()
        self._tab_devices.stop()
        self._tab_network.stop()
        self._discovery.stop()
        self._server_thread.stop()
        _save_config(self._config)
        event.accept()
