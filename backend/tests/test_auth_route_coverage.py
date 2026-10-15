"""Κάθε route του API απαντά 401 χωρίς session, εκτός από ρητή λίστα δημόσιων.

Η απαρίθμηση γίνεται από το app.openapi()["paths"] (δημόσιο API του
FastAPI, δουλεύει και με openapi_url=None), όχι από private πεδία. Κάθε path
ελέγχεται με πραγματικό request. Ένα νέο route χωρίς auth σπάει αυτό το test.

Εκτελείται standalone: `python tests/test_auth_route_coverage.py`
"""

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth_helpers import new_client  # noqa: E402

from app.api.main import app  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.db.database import init_db  # noqa: E402

PUBLIC_ROUTES = {
    ("get", "/api/health"),
    ("post", "/api/auth/login"),
}

_PATH_PARAM_RE = re.compile(r"\{[^}]+\}")


def _all_routes() -> list[tuple[str, str]]:
    return [
        (method, path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    ]


def _with_temp_db(test):
    def wrapper():
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db_path = Path(path)
        init_db(db_path)
        app.dependency_overrides[get_settings] = lambda: Settings(
            _env_file=None, DB_PATH=db_path, OLLAMA_URL="http://127.0.0.1:1"
        )
        try:
            test()
        finally:
            app.dependency_overrides.clear()
            os.remove(db_path)

    wrapper.__name__ = test.__name__
    return wrapper


def test_public_list_is_exact_and_exists():
    routes = set(_all_routes())
    assert PUBLIC_ROUTES <= routes, f"Δημόσια routes που δεν υπάρχουν πια: {PUBLIC_ROUTES - routes}"
    assert all(path.startswith("/api/") for _, path in routes), routes


@_with_temp_db
def test_every_non_public_route_is_401_without_session():
    client = new_client(app)
    checked = []
    for method, path in _all_routes():
        if (method, path) in PUBLIC_ROUTES:
            continue
        url = _PATH_PARAM_RE.sub("1", path)
        response = client.request(method.upper(), url, json={})
        assert response.status_code == 401, (
            f"{method.upper()} {path} -> {response.status_code} {response.text}"
        )
        checked.append((method, path))
    # Αν η απαρίθμηση άδειαζε, το test θα περνούσε χωρίς να ελέγχει τίποτα.
    assert len(checked) >= 11, checked


@_with_temp_db
def test_x_user_header_without_session_is_401_everywhere():
    client = new_client(app)
    for method, path in _all_routes():
        if (method, path) in PUBLIC_ROUTES:
            continue
        url = _PATH_PARAM_RE.sub("1", path)
        response = client.request(method.upper(), url, json={}, headers={"X-User": "admin"})
        assert response.status_code == 401, (
            f"{method.upper()} {path} με X-User -> {response.status_code}"
        )


@_with_temp_db
def test_public_routes_answer_without_session():
    client = new_client(app)
    assert client.get("/api/health").status_code == 200
    # Λάθος credentials: 401, όχι 403/500. Το login είναι προσβάσιμο ανώνυμα.
    response = client.post("/api/auth/login", json={"username": "nobody", "password": "x" * 12})
    assert response.status_code == 401


@_with_temp_db
def test_docs_and_openapi_are_not_served_by_default():
    assert Settings(_env_file=None).ENABLE_DOCS is False
    client = new_client(app)
    for url in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
        response = client.get(url)
        assert response.status_code == 404, f"{url} -> {response.status_code}"
        assert "swagger" not in response.text.lower()
        assert '"openapi"' not in response.text


def run_all():
    tests = [
        test_public_list_is_exact_and_exists,
        test_every_non_public_route_is_401_without_session,
        test_x_user_header_without_session_is_401_everywhere,
        test_public_routes_answer_without_session,
        test_docs_and_openapi_are_not_served_by_default,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
