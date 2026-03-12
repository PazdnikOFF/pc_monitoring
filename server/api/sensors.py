"""
FastAPI router: sensor data endpoints.

GET /api/sensors  — list of all sensor keys with label and unit
GET /api/data     — current values of all sensors
"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/sensors")
def list_sensors(request: Request):
    """Return metadata for all known sensors (key, label, unit)."""
    reader = request.app.state.mahm_reader
    sensors = reader.read_all()
    return [
        {
            "key": key,
            "label": entry.label,
            "unit": entry.unit,
            "gpu": entry.gpu,
            "src_id": entry.src_id,
        }
        for key, entry in sensors.items()
    ]


@router.get("/api/data")
def get_data(request: Request):
    """Return current sensor values."""
    reader = request.app.state.mahm_reader
    sensors = reader.read_all()
    return {
        key: {
            "value": entry.value,
            "unit": entry.unit,
            "label": entry.label,
        }
        for key, entry in sensors.items()
    }
