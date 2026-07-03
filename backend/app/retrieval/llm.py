"""Thin wrapper πάνω από το τοπικό Ollama chat API (qwen2.5:14b).

Χωρίς cloud κλήσεις — μόνο τοπικό endpoint (localhost). Η σύνδεση είναι lazy:
δεν γίνεται κανένα HTTP call πριν την πρώτη `.generate()`.
"""

import requests

from app.core.config import get_settings

MODEL_NAME = get_settings().OLLAMA_MODEL
DEFAULT_BASE_URL = get_settings().OLLAMA_URL
DEFAULT_TIMEOUT_S = 120


class OllamaClient:
    def __init__(
        self,
        model_name: str = MODEL_NAME,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT_S,
    ):
        self.model_name = model_name
        self.base_url = base_url
        self.timeout = timeout

    def generate(self, system: str, user: str) -> str:
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
