"""
WebSocket endpoint: /ws/data

Broadcasts current sensor readings to every connected client every
refresh_ms milliseconds (taken from app state config).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)

router = APIRouter()

# Global set of active WebSocket connections (managed per-app instance)
_connections: Set[WebSocket] = set()


def get_active_connections() -> Set[WebSocket]:
    """Expose the connection set for GUI inspection."""
    return _connections


@router.websocket("/ws/data")
async def ws_data(websocket: WebSocket) -> None:
    await websocket.accept()
    _connections.add(websocket)
    log.info(
        "WebSocket client connected: %s — total: %d",
        websocket.client,
        len(_connections),
    )

    app = websocket.app
    reader = app.state.mahm_reader
    config = app.state.config

    try:
        while True:
            refresh_ms: int = config.get("refresh_ms", 1000)
            sensors = reader.read_all()
            payload = {
                "timestamp": time.time(),
                "sensors": {
                    key: {
                        "value": entry.value,
                        "unit": entry.unit,
                        "label": entry.label,
                    }
                    for key, entry in sensors.items()
                },
            }
            try:
                await websocket.send_json(payload)
            except Exception:
                break

            await asyncio.sleep(refresh_ms / 1000.0)

    except WebSocketDisconnect:
        log.info("WebSocket client disconnected: %s", websocket.client)
    except Exception as exc:
        log.warning("WebSocket error (%s): %s", websocket.client, exc)
    finally:
        _connections.discard(websocket)
        log.info(
            "WebSocket connection closed: %s — total: %d",
            websocket.client,
            len(_connections),
        )
