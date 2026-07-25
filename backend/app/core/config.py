"""Κεντρικοποιημένο configuration μέσω pydantic-settings.

Οι default τιμές είναι αυτές που ίσχυαν hardcoded στον κώδικα πριν από αυτό
το refactor. Env vars (ή backend/.env, βλ. backend/.env.example) τις
υπερισχύουν. `get_settings()` είναι το singleton accessor — μία μόνο
ανάγνωση/parse των settings ανά process.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DB_PATH: Path = BASE_DIR / "data" / "evalassist.db"
    CHROMA_PATH: Path = BASE_DIR / "chroma_db"
    CHROMA_COLLECTION: str = "evaluation_chunks"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:14b"
    OLLAMA_GEN_MODEL: str = ""  # if empty, falls back to OLLAMA_MODEL
    OLLAMA_TIMEOUT_S: int = 120
    OLLAMA_TEMPERATURE: float = 0.0
    OLLAMA_SEED: int = 42
    TOP_K_RETRIEVE: int = 20
    TOP_K_RERANK: int = 5
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]

    @property
    def resolved_gen_model(self) -> str:
        return self.OLLAMA_GEN_MODEL or self.OLLAMA_MODEL


@lru_cache
def get_settings() -> Settings:
    return Settings()
