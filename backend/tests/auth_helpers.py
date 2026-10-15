"""Κοινά βοηθητικά auth για τα standalone API tests.

Δεν είναι test_*.py: το loop του CI (backend/tests/test_*.py) δεν το τρέχει
μόνο του. Μόνο συνθετικοί χρήστες και κωδικοί.

Το TestClient δουλεύει σε https://testserver: το session cookie είναι
Secure (COOKIE_SECURE=True by default) και σε http δεν ξαναστέλνεται."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import service
from app.db.database import get_connection

TEST_USERNAME = "tester"
TEST_PASSWORD = "synthetic-pass-0001"
BASE_URL = "https://testserver"


def make_user(
    db_path: Path,
    username: str = TEST_USERNAME,
    role: str = "user",
    password: str = TEST_PASSWORD,
    must_change_pw: bool = False,
) -> int:
    conn = get_connection(db_path)
    try:
        return service.create_user(
            conn,
            username,
            role,
            password,
            must_change_pw,
            datetime.now(timezone.utc),
            None,
            service.AuthEvent.ADMIN_BOOTSTRAP,
        )
    finally:
        conn.close()


def new_client(app: FastAPI) -> TestClient:
    return TestClient(app, base_url=BASE_URL)


def login(client: TestClient, username: str = TEST_USERNAME, password: str = TEST_PASSWORD):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response


def logged_in_client(
    app: FastAPI, db_path: Path, username: str = TEST_USERNAME, role: str = "user"
) -> TestClient:
    """Δημιουργεί συνθετικό χρήστη και επιστρέφει client με ενεργό session."""
    make_user(db_path, username, role)
    client = new_client(app)
    login(client, username)
    return client


class FakeClock:
    """Ψεύτικο ρολόι για app.auth.deps.get_clock (lockout, λήξη session)."""

    def __init__(self, start: datetime = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)
