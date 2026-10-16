"""Δημόσιο health check: /api/health. Κανένα δεδομένο ή πλήθος, μόνο αν το
API τρέχει και, με το semantic ανοιχτό, αν το τοπικό Ollama απαντά.

Με SEMANTIC_ENABLED=false το Ollama δεν χρησιμοποιείται, άρα δεν καλείται
καθόλου: ollama_reachable=null σημαίνει "δεν ελέγχθηκε", όχι βλάβη. Το flag
το μαθαίνει το frontend ΜΟΝΟ από το features.semantic_enabled του /api/auth/me,
όχι από εδώ."""

import httpx
from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings

router = APIRouter()


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    if not settings.SEMANTIC_ENABLED:
        return {"status": "ok", "ollama_reachable": None}
    ollama_reachable = False
    try:
        response = httpx.get(f"{settings.OLLAMA_URL}/api/tags", timeout=1.0)
        ollama_reachable = response.status_code == 200
    except Exception:
        ollama_reachable = False
    return {"status": "ok", "ollama_reachable": ollama_reachable}
