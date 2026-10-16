"""Mini test/sample flow για το backend/app/core/config.py (refactor step).

Καλύπτει:
  - defaults: οι τιμές που ίσχυαν hardcoded στον κώδικα πριν από αυτό το
    refactor παραμένουν οι ίδιες.
  - env override: μεταβλητές περιβάλλοντος υπερισχύουν των defaults.
  - get_settings(): singleton (lru_cache) accessor.
  - .env με UTF-8 BOM: η πρώτη ρύθμιση εφαρμόζεται (utf-8-sig), όπως και
    χωρίς BOM, και οι ελληνικοί χαρακτήρες διαβάζονται σωστά και στα δύο.

Εκτελείται standalone: `python tests/test_config.py`
"""

import os
import sys
import tempfile
from contextlib import contextmanager
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
    assert settings.OLLAMA_TEMPERATURE == 0.0
    assert settings.OLLAMA_SEED == 42
    assert settings.OLLAMA_NUM_CTX == 8192
    assert settings.OLLAMA_KEEP_ALIVE == "30m"
    assert settings.TOP_K_RETRIEVE == 20
    assert settings.TOP_K_RERANK == 5
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


def test_deterministic_generation_env_override():
    os.environ["OLLAMA_TEMPERATURE"] = "0.7"
    os.environ["OLLAMA_SEED"] = "1337"
    os.environ["OLLAMA_NUM_CTX"] = "4096"
    os.environ["OLLAMA_KEEP_ALIVE"] = "1h"
    try:
        settings = Settings(_env_file=None)
        assert settings.OLLAMA_TEMPERATURE == 0.7
        assert settings.OLLAMA_SEED == 1337
        assert settings.OLLAMA_NUM_CTX == 4096
        assert settings.OLLAMA_KEEP_ALIVE == "1h"
    finally:
        del os.environ["OLLAMA_TEMPERATURE"]
        del os.environ["OLLAMA_SEED"]
        del os.environ["OLLAMA_NUM_CTX"]
        del os.environ["OLLAMA_KEEP_ALIVE"]


UTF8_BOM = b"\xef\xbb\xbf"
UNIQUE_DB_PATH = "/tmp/env-bom-unique-5c1e/evalassist.db"
# Ρυθμίσεις που ορίζουν τα .env αυτών των tests: δεν πρέπει να έρχονται από
# το περιβάλλον της διεργασίας, που υπερισχύει του αρχείου.
_ENV_FILE_KEYS = ("DB_PATH", "SESSION_HOURS", "OLLAMA_GEN_MODEL")


@contextmanager
def _env_file(body: str, bom: bool):
    """Προσωρινό .env (με ή χωρίς BOM). Το Settings το διαβάζει με το
    env_file_encoding του model_config, όπως το backend/.env."""
    saved = {key: os.environ.pop(key) for key in _ENV_FILE_KEYS if key in os.environ}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ".env"
        path.write_bytes((UTF8_BOM if bom else b"") + body.encode("utf-8"))
        try:
            yield path
        finally:
            os.environ.update(saved)


def _posix(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def test_env_file_with_bom_applies_first_setting():
    with _env_file(f"DB_PATH={UNIQUE_DB_PATH}\nSESSION_HOURS=3\n", bom=True) as path:
        assert path.read_bytes().startswith(UTF8_BOM)
        settings = Settings(_env_file=path)
    assert _posix(settings.DB_PATH) == UNIQUE_DB_PATH
    assert settings.SESSION_HOURS == 3


def test_env_file_without_bom_applies_first_setting():
    with _env_file(f"DB_PATH={UNIQUE_DB_PATH}\nSESSION_HOURS=3\n", bom=False) as path:
        assert not path.read_bytes().startswith(UTF8_BOM)
        settings = Settings(_env_file=path)
    assert _posix(settings.DB_PATH) == UNIQUE_DB_PATH
    assert settings.SESSION_HOURS == 3


def test_env_file_greek_values_with_and_without_bom():
    greek_db = "/tmp/φάκελος-δοκιμής/αξιολογήσεις.db"
    greek_model = "μοντέλο-Ελληνικά-ΆΈΉ-ϊΰ"
    body = f"DB_PATH={greek_db}\nOLLAMA_GEN_MODEL={greek_model}\n"
    for bom in (True, False):
        with _env_file(body, bom=bom) as path:
            settings = Settings(_env_file=path)
        assert _posix(settings.DB_PATH) == greek_db, bom
        assert settings.OLLAMA_GEN_MODEL == greek_model, bom


def run_all():
    tests = [
        test_defaults_match_previous_hardcoded_values,
        test_env_override,
        test_get_settings_is_a_cached_singleton,
        test_resolved_gen_model_falls_back_to_ollama_model,
        test_deterministic_generation_env_override,
        test_env_file_with_bom_applies_first_setting,
        test_env_file_without_bom_applies_first_setting,
        test_env_file_greek_values_with_and_without_bom,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
