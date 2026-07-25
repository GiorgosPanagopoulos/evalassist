"""Thin wrapper πάνω από το τοπικό Ollama chat API.
Χωρίς cloud κλήσεις, μόνο τοπικό endpoint (localhost). Η σύνδεση είναι lazy:
δεν γίνεται κανένα HTTP call πριν την πρώτη `.generate()`.
"""
import requests

from app.core.config import get_settings


class OllamaClient:
    def __init__(
        self,
        model_name: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ):
        settings = get_settings()
        self.model_name = model_name if model_name is not None else settings.OLLAMA_MODEL
        self.base_url = base_url if base_url is not None else settings.OLLAMA_URL
        self.timeout = timeout if timeout is not None else settings.OLLAMA_TIMEOUT_S
        self.temperature = (
            temperature if temperature is not None else settings.OLLAMA_TEMPERATURE
        )
        self.seed = seed if seed is not None else settings.OLLAMA_SEED

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
                "options": {
                    "temperature": self.temperature,
                    "seed": self.seed,
                },
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
