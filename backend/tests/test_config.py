"""Mini test/sample flow για το backend/app/core/config.py (refactor step).

Καλύπτει:
  - defaults: οι τιμές που ίσχυαν hardcoded στον κώδικα πριν από αυτό το
    refactor παραμένουν οι ίδιες.
  - env override: μεταβλητές περιβάλλοντος υπερισχύουν των defaults.
  - get_settings(): singleton (lru_cache) accessor.

Εκτελείται standalone: `python tests/test_config.py`
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings, get_settings  # noqa: E402


def test_defaults_match_previous_hardcoded_values():
    settings = Settings(_env_file=None)
    assert settings.CHROMA_COLLECTION == "evaluation_chunks"
    assert settings.EMBEDDING_MODEL == "BAAI/bge-m3"
    assert settings.RERANKER_MODEL == "BAAI/bge-reranker-v2-m3"
    assert settings.OLLAMA_URL == "http://localhost:11434"
    assert settings.OLLAMA_MODEL == "qwen2.5:14b"
    assert settings.OLLAMA_GEN_MODEL == ""
    assert settings.OLLAMA_TIMEOUT_S == 120
    assert settings.TOP_K_RETRIEVE == 20
    assert settings.TOP_K_RERANK == 5
    assert settings.ALLOWED_ORIGINS == ["http://localhost:5173"]
    assert settings.DB_PATH.name == "evalassist.db"
    assert settings.CHROMA_PATH.name == "chroma_db"


def test_env_override():
    os.environ["OLLAMA_MODEL"] = "test-model-override"
    os.environ["TOP_K_RERANK"] = "7"
    try:
        settings = Settings(_env_file=None)
        assert settings.OLLAMA_MODEL == "test-model-override"
        assert settings.TOP_K_RERANK == 7
    finally:
        del os.environ["OLLAMA_MODEL"]
        del os.environ["TOP_K_RERANK"]


def test_get_settings_is_a_cached_singleton():
    assert get_settings() is get_settings()


def test_resolved_gen_model_falls_back_to_ollama_model():
    settings = Settings(_env_file=None, OLLAMA_GEN_MODEL="")
    assert settings.resolved_gen_model == settings.OLLAMA_MODEL

    settings = Settings(_env_file=None, OLLAMA_GEN_MODEL="hf.co/ilsp/Llama-Krikri-8B-Instruct-GGUF:Q4_K_M")
    assert settings.resolved_gen_model == "hf.co/ilsp/Llama-Krikri-8B-Instruct-GGUF:Q4_K_M"


def run_all():
    tests = [
        test_defaults_match_previous_hardcoded_values,
        test_env_override,
        test_get_settings_is_a_cached_singleton,
        test_resolved_gen_model_falls_back_to_ollama_model,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
