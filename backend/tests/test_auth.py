"""Login, sessions, lockout, must_change_pw, ρόλοι και διαχείριση χρηστών.

Μόνο συνθετικοί χρήστες. Το ρολόι είναι ψεύτικο (FakeClock μέσω override του
app.auth.deps.get_clock), ώστε λήξη και lockout να ελέγχονται χωρίς αναμονή.

Εκτελείται standalone: `python tests/test_auth.py`
"""

import hashlib
import os
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth_helpers import TEST_PASSWORD, FakeClock, login, make_user, new_client  # noqa: E402

from app.api.main import app  # noqa: E402
from app.auth.deps import SESSION_COOKIE, get_clock  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.db.database import init_db  # noqa: E402

LOGIN = "/api/auth/login"
ME = "/api/auth/me"
DATA_URL = "/api/persons"
TIMELINE_URL = "/api/person/Μ-00000/timeline"


@contextmanager
def _env():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    init_db(db_path)
    clock = FakeClock()
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, DB_PATH=db_path)
    app.dependency_overrides[get_clock] = lambda: clock
    try:
        yield db_path, clock
    finally:
        app.dependency_overrides.clear()
        os.remove(db_path)


def _post_login(client, username, password):
    return client.post(LOGIN, json={"username": username, "password": password})


def _user_row(db_path: Path, username: str) -> sqlite3.Row:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    finally:
        conn.close()


def _auth_events(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [r[0] for r in conn.execute("SELECT event FROM auth_log ORDER BY id")]
    finally:
        conn.close()


def _all_text_values(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        values = []
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        for table in tables:
            for row in conn.execute(f'SELECT * FROM "{table}"'):
                values.extend(str(v) for v in row if v is not None)
        return values
    finally:
        conn.close()


def _session_token(response) -> str:
    return response.cookies[SESSION_COOKIE]


# --- login -------------------------------------------------------------------


def test_wrong_password_and_unknown_user_same_status_and_body():
    with _env() as (db_path, _):
        make_user(db_path, "alice")
        client = new_client(app)
        wrong = _post_login(client, "alice", "wrong-password-xx")
        unknown = _post_login(client, "nobody", "wrong-password-xx")
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json()
        assert SESSION_COOKIE not in wrong.cookies and SESSION_COOKIE not in unknown.cookies


def test_unknown_username_is_never_stored():
    # Κάποιος γράφει τον κωδικό του στο πεδίο username: το κείμενο δεν πρέπει
    # να μείνει πουθενά. Η σάρωση είναι case-insensitive, γιατί το username
    # κανονικοποιείται σε πεζά πριν από οποιαδήποτε εγγραφή.
    typed = "Secret-Pass-123"
    with _env() as (db_path, _):
        make_user(db_path, "alice")
        response = _post_login(new_client(app), typed, "anything-at-all")
        assert response.status_code == 401

        leaked = [v for v in _all_text_values(db_path) if typed.lower() in v.lower()]
        assert not leaked, leaked

        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT event, username, detail FROM auth_log WHERE event = 'login_fail'"
            ).fetchall()
        finally:
            conn.close()
        assert rows == [("login_fail", None, "unknown_user")]


def test_successful_login_sets_hardened_cookie():
    with _env() as (db_path, _):
        make_user(db_path, "alice")
        response = _post_login(new_client(app), "alice", TEST_PASSWORD)
        assert response.status_code == 200
        assert response.json() == {
            "id": 1,
            "username": "alice",
            "role": "user",
            "must_change_pw": False,
            "features": {"semantic_enabled": False},
        }
        set_cookie = response.headers["set-cookie"].lower()
        for flag in ("httponly", "secure", "samesite=strict", "path=/", "max-age=28800"):
            assert flag in set_cookie, (flag, set_cookie)


def test_username_is_case_insensitive():
    with _env() as (db_path, _):
        make_user(db_path, "alice")
        assert _post_login(new_client(app), "  ALICE ", TEST_PASSWORD).status_code == 200


# --- lockout -----------------------------------------------------------------


def _fail_n(client, username, n):
    for _ in range(n):
        assert _post_login(client, username, "wrong-password-xx").status_code == 401


def test_lockout_after_5_failures_and_unlock_after_expiry():
    with _env() as (db_path, clock):
        make_user(db_path, "alice")
        client = new_client(app)

        _fail_n(client, "alice", 4)
        assert _user_row(db_path, "alice")["locked_until"] is None
        _fail_n(client, "alice", 1)
        assert _user_row(db_path, "alice")["locked_until"] is not None
        assert "lockout" in _auth_events(db_path)

        locked = _post_login(client, "alice", TEST_PASSWORD)
        assert locked.status_code == 401

        clock.advance(minutes=14, seconds=59)
        assert _post_login(client, "alice", TEST_PASSWORD).status_code == 401

        clock.advance(seconds=1)
        assert _post_login(client, "alice", TEST_PASSWORD).status_code == 200
        row = _user_row(db_path, "alice")
        assert row["failed_attempts"] == 0 and row["locked_until"] is None


def test_correct_password_while_locked_is_401_same_body_and_changes_nothing():
    with _env() as (db_path, clock):
        make_user(db_path, "alice")
        client = new_client(app)
        _fail_n(client, "alice", 5)
        wrong_body = _post_login(client, "nobody", "wrong-password-xx").json()
        before = dict(_user_row(db_path, "alice"))

        # Δοκιμές με τον σωστό κωδικό όσο διαρκεί το κλείδωμα: καμία δεν
        # περνά, καμία δεν μηδενίζει μετρητή ή παρατείνει/κόβει το κλείδωμα.
        for _ in range(10):
            clock.advance(seconds=30)
            response = _post_login(client, "alice", TEST_PASSWORD)
            assert response.status_code == 401
            assert response.json() == wrong_body
            assert SESSION_COOKIE not in response.cookies
            after = dict(_user_row(db_path, "alice"))
            assert after["failed_attempts"] == before["failed_attempts"]
            assert after["locked_until"] == before["locked_until"]
        assert _auth_events(db_path).count("login_locked") == 10


def test_disabled_user_login_is_same_401():
    with _env() as (db_path, _):
        make_user(db_path, "root", role="admin")
        make_user(db_path, "alice")
        admin = new_client(app)
        login(admin, "root")
        assert admin.post("/api/admin/users/2/disable").status_code == 204
        wrong_body = _post_login(new_client(app), "nobody", "wrong-password-xx").json()
        response = _post_login(new_client(app), "alice", TEST_PASSWORD)
        assert response.status_code == 401 and response.json() == wrong_body


# --- sessions ----------------------------------------------------------------


def test_expired_session_is_401():
    with _env() as (db_path, clock):
        make_user(db_path, "alice")
        client = new_client(app)
        login(client, "alice")
        clock.advance(hours=7, minutes=59)
        assert client.get(ME).status_code == 200
        clock.advance(minutes=1)
        assert client.get(ME).status_code == 401
        assert client.get(DATA_URL).status_code == 401


def test_logout_invalidates_session_server_side():
    with _env() as (db_path, _):
        make_user(db_path, "alice")
        client = new_client(app)
        token = _session_token(login(client, "alice"))
        assert client.post("/api/auth/logout").status_code == 204
        assert client.get(ME).status_code == 401
        # Το παλιό token, αν το κράτησε κάποιος, δεν ισχύει πια.
        replay = new_client(app)
        replay.cookies.set(SESSION_COOKIE, token)
        assert replay.get(ME).status_code == 401
        assert "logout" in _auth_events(db_path)


def test_disable_kills_existing_sessions_immediately():
    with _env() as (db_path, _):
        make_user(db_path, "root", role="admin")
        make_user(db_path, "alice")
        user = new_client(app)
        login(user, "alice")
        assert user.get(DATA_URL).status_code == 200

        admin = new_client(app)
        login(admin, "root")
        assert admin.post("/api/admin/users/2/disable").status_code == 204
        assert user.get(DATA_URL).status_code == 401
        assert user.get(ME).status_code == 401


def test_forged_cookie_is_401():
    with _env() as (db_path, _):
        make_user(db_path, "alice")
        client = new_client(app)
        client.cookies.set(SESSION_COOKIE, "not-a-real-token")
        assert client.get(ME).status_code == 401


# --- X-User / audit ------------------------------------------------------------


def test_x_user_without_session_is_401():
    with _env() as (db_path, _):
        response = new_client(app).get(TIMELINE_URL, headers={"X-User": "alice"})
        assert response.status_code == 401


def test_audit_records_session_user_not_x_user():
    with _env() as (db_path, _):
        make_user(db_path, "alice")
        make_user(db_path, "bob")
        client = new_client(app)
        login(client, "alice")
        response = client.get(TIMELINE_URL, headers={"X-User": "bob"})
        assert response.status_code == 200
        conn = sqlite3.connect(db_path)
        try:
            users = [r[0] for r in conn.execute("SELECT user FROM audit_log")]
        finally:
            conn.close()
        assert users == ["alice"]


# --- must_change_pw ------------------------------------------------------------


def test_must_change_pw_is_403_until_password_changed():
    with _env() as (db_path, _):
        make_user(db_path, "alice", must_change_pw=True)
        client = new_client(app)
        assert login(client, "alice").json()["must_change_pw"] is True

        assert client.get(DATA_URL).status_code == 403
        assert client.get(TIMELINE_URL).status_code == 403
        assert client.get(ME).status_code == 200

        change = "/api/auth/change-password"
        too_short = client.post(
            change, json={"current_password": TEST_PASSWORD, "new_password": "short"}
        )
        assert too_short.status_code == 400
        wrong_current = client.post(
            change,
            json={"current_password": "wrong-password-xx", "new_password": "a-new-synthetic-pass"},
        )
        assert wrong_current.status_code == 400
        same = client.post(
            change, json={"current_password": TEST_PASSWORD, "new_password": TEST_PASSWORD}
        )
        assert same.status_code == 400
        assert client.get(DATA_URL).status_code == 403

        ok = client.post(
            change, json={"current_password": TEST_PASSWORD, "new_password": "a-new-synthetic-pass"}
        )
        assert ok.status_code == 204
        assert client.get(DATA_URL).status_code == 200
        assert client.get(ME).json()["must_change_pw"] is False


def test_change_password_kills_other_sessions_keeps_current():
    with _env() as (db_path, _):
        make_user(db_path, "alice")
        first = new_client(app)
        login(first, "alice")
        second = new_client(app)
        login(second, "alice")
        response = second.post(
            "/api/auth/change-password",
            json={"current_password": TEST_PASSWORD, "new_password": "a-new-synthetic-pass"},
        )
        assert response.status_code == 204
        assert second.get(ME).status_code == 200
        assert first.get(ME).status_code == 401


# --- ρόλοι / admin ---------------------------------------------------------------


def test_user_gets_403_on_every_admin_route():
    with _env() as (db_path, _):
        make_user(db_path, "alice")
        client = new_client(app)
        login(client, "alice")
        admin_routes = [
            (method, path.replace("{user_id}", "1"))
            for path, ops in app.openapi()["paths"].items()
            if path.startswith("/api/admin/")
            for method in ops
        ]
        assert len(admin_routes) == 4, admin_routes
        for method, url in admin_routes:
            response = client.request(
                method.upper(), url, json={"username": "mallory", "role": "admin"}
            )
            assert response.status_code == 403, (method, url, response.status_code)
        assert _user_row(db_path, "mallory") is None


def test_admin_creates_user_with_temp_password_and_must_change():
    with _env() as (db_path, _):
        make_user(db_path, "root", role="admin")
        admin = new_client(app)
        login(admin, "root")

        created = admin.post("/api/admin/users", json={"username": "Carol", "role": "user"})
        assert created.status_code == 201
        assert created.headers["cache-control"] == "no-store"
        body = created.json()
        assert body["username"] == "carol" and body["role"] == "user"
        temp = body["temp_password"]
        assert len(temp) >= 12

        duplicate = admin.post("/api/admin/users", json={"username": "carol", "role": "user"})
        assert duplicate.status_code == 409
        invalid = admin.post("/api/admin/users", json={"username": "a b", "role": "user"})
        assert invalid.status_code == 409

        user = new_client(app)
        assert login(user, "carol", temp).json()["must_change_pw"] is True
        assert user.get(DATA_URL).status_code == 403

        listed = {u["username"]: u for u in admin.get("/api/admin/users").json()}
        assert set(listed) == {"root", "carol"}
        assert listed["carol"]["must_change_pw"] is True and listed["carol"]["is_active"] is True
        assert temp not in str(listed)


def test_admin_reset_password_kills_sessions_and_unlocks():
    with _env() as (db_path, _):
        make_user(db_path, "root", role="admin")
        make_user(db_path, "alice")
        user = new_client(app)
        login(user, "alice")
        _fail_n(new_client(app), "alice", 5)

        admin = new_client(app)
        login(admin, "root")
        reset = admin.post("/api/admin/users/2/reset-password")
        assert reset.status_code == 200
        temp = reset.json()["temp_password"]

        assert user.get(ME).status_code == 401
        relogin = new_client(app)
        assert login(relogin, "alice", temp).json()["must_change_pw"] is True
        assert admin.post("/api/admin/users/99/reset-password").status_code == 404


def test_last_active_admin_cannot_be_disabled():
    with _env() as (db_path, _):
        make_user(db_path, "root", role="admin")
        admin = new_client(app)
        login(admin, "root")
        assert admin.post("/api/admin/users/1/disable").status_code == 409
        assert _user_row(db_path, "root")["is_active"] == 1
        assert admin.get(ME).status_code == 200

        make_user(db_path, "second", role="admin")
        assert admin.post("/api/admin/users/2/disable").status_code == 204
        # Ο second είναι πλέον ανενεργός, άρα ο root είναι ξανά ο τελευταίος.
        assert admin.post("/api/admin/users/1/disable").status_code == 409
        assert admin.post("/api/admin/users/99/disable").status_code == 404


# --- τι μένει στη βάση -------------------------------------------------------------


def test_db_contains_no_raw_token_and_no_password():
    with _env() as (db_path, _):
        make_user(db_path, "root", role="admin")
        make_user(db_path, "alice", must_change_pw=True)
        secrets_seen = [TEST_PASSWORD]

        admin = new_client(app)
        secrets_seen.append(_session_token(login(admin, "root")))
        secrets_seen.append(
            admin.post("/api/admin/users", json={"username": "carol", "role": "user"}).json()[
                "temp_password"
            ]
        )
        secrets_seen.append(admin.post("/api/admin/users/2/reset-password").json()["temp_password"])

        user = new_client(app)
        token = _session_token(login(user, "alice", secrets_seen[-1]))
        secrets_seen.append(token)
        new_password = "a-new-synthetic-pass"
        secrets_seen.append(new_password)
        assert (
            user.post(
                "/api/auth/change-password",
                json={"current_password": secrets_seen[-3], "new_password": new_password},
            ).status_code
            == 204
        )
        _post_login(new_client(app), "alice", "typo-in-password-x")
        secrets_seen.append("typo-in-password-x")

        values = _all_text_values(db_path)
        for secret in secrets_seen:
            leaked = [v for v in values if secret in v]
            assert not leaked, (secret, leaked)

        conn = sqlite3.connect(db_path)
        try:
            hashes = {r[0] for r in conn.execute("SELECT token_hash FROM sessions")}
        finally:
            conn.close()
        assert hashlib.sha256(token.encode()).hexdigest() in hashes


def run_all():
    tests = [
        test_wrong_password_and_unknown_user_same_status_and_body,
        test_unknown_username_is_never_stored,
        test_successful_login_sets_hardened_cookie,
        test_username_is_case_insensitive,
        test_lockout_after_5_failures_and_unlock_after_expiry,
        test_correct_password_while_locked_is_401_same_body_and_changes_nothing,
        test_disabled_user_login_is_same_401,
        test_expired_session_is_401,
        test_logout_invalidates_session_server_side,
        test_disable_kills_existing_sessions_immediately,
        test_forged_cookie_is_401,
        test_x_user_without_session_is_401,
        test_audit_records_session_user_not_x_user,
        test_must_change_pw_is_403_until_password_changed,
        test_change_password_kills_other_sessions_keeps_current,
        test_user_gets_403_on_every_admin_route,
        test_admin_creates_user_with_temp_password_and_must_change,
        test_admin_reset_password_kills_sessions_and_unlocks,
        test_last_active_admin_cannot_be_disabled,
        test_db_contains_no_raw_token_and_no_password,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
