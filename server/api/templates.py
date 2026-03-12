"""
FastAPI router: template CRUD.

Templates are stored as individual JSON files in server/data/templates/.

GET    /api/templates         — list all templates
GET    /api/templates/{name}  — get single template
POST   /api/templates         — create or update template
DELETE /api/templates/{name}  — delete template
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.paths import TEMPLATES_DIR

router = APIRouter()

_TEMPLATES_DIR = TEMPLATES_DIR
_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------
# Pydantic models
# ------------------------------------------------------------------

class TemplatePage(BaseModel):
    duration_s: int = 5
    rows: List[str] = []


class Template(BaseModel):
    name: str
    refresh_ms: int = 1000
    pages: List[TemplatePage] = []


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _template_path(name: str) -> Path:
    # Sanitise name to prevent path traversal
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_", " "))
    return _TEMPLATES_DIR / f"{safe}.json"


def _load_template(name: str) -> Dict[str, Any]:
    p = _template_path(name)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")
    return json.loads(p.read_text(encoding="utf-8"))


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/api/templates")
def list_templates() -> List[Dict[str, Any]]:
    """Return a list of all template objects."""
    result = []
    for p in sorted(_TEMPLATES_DIR.glob("*.json")):
        try:
            result.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return result


@router.get("/api/templates/{name}")
def get_template(name: str) -> Dict[str, Any]:
    return _load_template(name)


@router.post("/api/templates", status_code=201)
def save_template(template: Template) -> Dict[str, Any]:
    """Create or overwrite a template."""
    p = _template_path(template.name)
    data = template.model_dump()
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


@router.delete("/api/templates/{name}", status_code=204)
def delete_template(name: str) -> None:
    p = _template_path(name)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")
    p.unlink()
