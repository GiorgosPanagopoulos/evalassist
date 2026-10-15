"""Δημόσιο health check: /api/health. Κανένα δεδομένο ή πλήθος, μόνο αν το
API τρέχει και αν το τοπικό Ollama απαντά."""

import httpx
from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings

router = APIRouter()


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    ollama_reachable = False
    try:
        response = httpx.get(f"{settings.OLLAMA_URL}/api/tags", timeout=1.0)
        ollama_reachable = response.status_code == 200
    except Exception:
        ollama_reachable = False
    return {"status": "ok", "ollama_reachable": ollama_reachable}
