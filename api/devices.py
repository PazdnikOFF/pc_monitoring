"""
FastAPI router: device management and binding.

GET    /api/devices            — list bound devices
GET    /api/devices/discovered — list devices found in the network
POST   /api/bind               — bind a device
POST   /api/bind/confirm       — force-rebind a device
DELETE /api/devices/{id}       — unbind a device
PATCH  /api/devices/{id}       — update alias / template
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


# ------------------------------------------------------------------
# Pydantic request bodies
# ------------------------------------------------------------------

class BindRequest(BaseModel):
    device_id: str
    ip: str


class ConfirmBindRequest(BaseModel):
    device_id: str
    ip: str
    force: bool = True


class PatchDeviceRequest(BaseModel):
    alias: Optional[str] = None
    template: Optional[str] = None


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/api/devices")
def list_devices(request: Request) -> List[Dict[str, Any]]:
    """Return all bound devices."""
    bm = request.app.state.binding_manager
    return [
        {
            "device_id": d.device_id,
            "mac": d.mac,
            "display": d.display,
            "alias": d.alias,
            "active_template": d.active_template,
            "last_seen": d.last_seen,
        }
        for d in bm.get_all_devices()
    ]


@router.get("/api/devices/discovered")
def list_discovered(request: Request) -> List[Dict[str, Any]]:
    """Return devices discovered on the network via UDP beacon."""
    ds = request.app.state.discovery_service
    return [
        {
            "device_id": d.device_id,
            "mac": d.mac,
            "display": d.display,
            "firmware": d.firmware,
            "bound_to": d.bound_to,
            "bound_pc_id": d.bound_pc_id,
            "ip": d.ip,
            "last_seen": d.last_seen,
        }
        for d in ds.get_all_devices()
    ]


@router.post("/api/bind", status_code=201)
def bind_device(req: BindRequest, request: Request) -> Dict[str, Any]:
    """Bind a discovered device to this PC."""
    cfg = request.app.state.config
    ds = request.app.state.discovery_service
    bm = request.app.state.binding_manager

    discovered = ds.get_device(req.device_id)
    if not discovered:
        raise HTTPException(status_code=404, detail="Device not found in discovered list")

    # Check if already bound to another PC
    if discovered.bound_pc_id and discovered.bound_pc_id != cfg["pc_id"]:
        raise HTTPException(
            status_code=409,
            detail=f"Device is bound to another PC: {discovered.bound_to}",
        )

    ds.send_bind_command(
        ip=req.ip,
        device_id=req.device_id,
        pc_id=cfg["pc_id"],
        pc_name=cfg["pc_name"],
    )

    dev = bm.bind(
        device_id=discovered.device_id,
        mac=discovered.mac,
        display=discovered.display,
    )
    return {
        "device_id": dev.device_id,
        "mac": dev.mac,
        "display": dev.display,
        "alias": dev.alias,
        "active_template": dev.active_template,
        "last_seen": dev.last_seen,
    }


@router.post("/api/bind/confirm", status_code=201)
def confirm_bind(req: ConfirmBindRequest, request: Request) -> Dict[str, Any]:
    """Force-rebind a device that is currently bound to another PC."""
    cfg = request.app.state.config
    ds = request.app.state.discovery_service
    bm = request.app.state.binding_manager

    discovered = ds.get_device(req.device_id)
    if not discovered:
        raise HTTPException(status_code=404, detail="Device not found in discovered list")

    ds.send_bind_command(
        ip=req.ip,
        device_id=req.device_id,
        pc_id=cfg["pc_id"],
        pc_name=cfg["pc_name"],
        force=True,
    )

    dev = bm.bind(
        device_id=discovered.device_id,
        mac=discovered.mac,
        display=discovered.display,
    )
    return {
        "device_id": dev.device_id,
        "mac": dev.mac,
        "display": dev.display,
        "alias": dev.alias,
        "active_template": dev.active_template,
        "last_seen": dev.last_seen,
    }


@router.delete("/api/devices/{device_id}", status_code=204)
def unbind_device(device_id: str, request: Request) -> None:
    """Unbind (remove) a device."""
    bm = request.app.state.binding_manager
    ds = request.app.state.discovery_service
    cfg = request.app.state.config

    if bm.get_device(device_id) is None:
        raise HTTPException(status_code=404, detail="Device not bound")

    # Best-effort UDP unbind if device is online
    discovered = ds.get_device(device_id)
    if discovered:
        ds.send_unbind_command(ip=discovered.ip, device_id=device_id)

    bm.unbind(device_id)


@router.patch("/api/devices/{device_id}")
def patch_device(
    device_id: str, body: PatchDeviceRequest, request: Request
) -> Dict[str, Any]:
    """Update alias and/or active template of a bound device."""
    bm = request.app.state.binding_manager
    dev = bm.get_device(device_id)
    if dev is None:
        raise HTTPException(status_code=404, detail="Device not bound")

    if body.alias is not None:
        bm.set_alias(device_id, body.alias)
    if body.template is not None:
        bm.set_template(device_id, body.template)

    dev = bm.get_device(device_id)  # reload after mutation
    return {
        "device_id": dev.device_id,
        "mac": dev.mac,
        "display": dev.display,
        "alias": dev.alias,
        "active_template": dev.active_template,
        "last_seen": dev.last_seen,
    }
