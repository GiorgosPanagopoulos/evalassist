"""Λογική auth πάνω στους πίνακες users, sessions, auth_log.

Κανένα HTTP εδώ: οι domain exceptions γίνονται map σε status codes στους
routers. Ο χρόνος (now) περνάει πάντα ως όρισμα από το ρολόι της εφαρμογής
(app.auth.deps.get_clock), ποτέ datetime.now() εδώ μέσα, ώστε τα tests να
ελέγχουν lockout και λήξη με ψεύτικο ρολόι.

Κωδικοί και raw tokens δεν γράφονται ποτέ στη βάση ή στο auth_log."""

import hashlib
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from app.auth.passwords import (
    MIN_PASSWORD_LENGTH,
    dummy_verify,
    generate_temp_password,
    hash_password,
    verify_password,
)
from app.core.exceptions import NotFoundError

LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION = timedelta(minutes=15)
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,64}$")
ROLES = ("admin", "user")


class AuthEvent(StrEnum):
    LOGIN_OK = "login_ok"
    LOGIN_FAIL = "login_fail"
    LOGIN_LOCKED = "login_locked"
    LOCKOUT = "lockout"
    LOGOUT = "logout"
    PASSWORD_CHANGE = "password_change"
    ADMIN_CREATE_USER = "admin_create_user"
    ADMIN_DISABLE_USER = "admin_disable_user"
    ADMIN_RESET_PASSWORD = "admin_reset_password"
    ADMIN_BOOTSTRAP = "admin_bootstrap"


class InvalidCredentialsError(Exception):
    """Άγνωστος χρήστης, λάθος κωδικός, κλειδωμένος ή ανενεργός λογαριασμός.
    Σκόπιμα ΕΝΑ exception για όλα: ο καλών δεν μπορεί να τα ξεχωρίσει."""


class PasswordPolicyError(Exception):
    """Ο νέος κωδικός δεν πληροί την πολιτική (μήκος, ίδιος με τον τρέχοντα)."""


class UsernameError(Exception):
    """Μη έγκυρο ή ήδη υπάρχον username."""


class LastAdminError(Exception):
    """Απόπειρα απενεργοποίησης του τελευταίου ενεργού admin."""


@dataclass(frozen=True)
class SessionRecord:
    token_hash: str
    user_id: int
    username: str
    role: str
    must_change_pw: bool


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def normalize_username(raw: str) -> str:
    return raw.strip().lower()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def check_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Ο κωδικός πρέπει να έχει τουλάχιστον {MIN_PASSWORD_LENGTH} χαρακτήρες."
        )


def log_event(
    conn: sqlite3.Connection,
    now: datetime,
    event: AuthEvent,
    username: str | None = None,
    actor_user_id: int | None = None,
    target_user_id: int | None = None,
    detail: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO auth_log (ts, event, username, actor_user_id, target_user_id, detail)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            iso(now),
            str(event),
            username[:64] if username else username,
            actor_user_id,
            target_user_id,
            detail,
        ),
    )


# --- login / sessions -------------------------------------------------------


def authenticate(
    conn: sqlite3.Connection, username: str, password: str, now: datetime
) -> sqlite3.Row:
    """Επιστρέφει τη γραμμή του χρήστη ή σηκώνει InvalidCredentialsError.

    Σε κάθε κλάδο τρέχει ακριβώς ένα scrypt, ώστε ο χρόνος να μην ξεχωρίζει
    άγνωστο χρήστη, λάθος κωδικό, κλείδωμα ή απενεργοποίηση. Όσο ο
    λογαριασμός είναι κλειδωμένος, ακόμη και ο σωστός κωδικός απορρίπτεται
    και ΔΕΝ αγγίζει ούτε τον μετρητή ούτε τη λήξη του κλειδώματος."""
    name = normalize_username(username)
    row = conn.execute("SELECT * FROM users WHERE username = ?", (name,)).fetchone()

    if row is None:
        dummy_verify(password)
        # Το πληκτρολογημένο username ΔΕΝ γράφεται: για άγνωστο χρήστη μπορεί
        # να είναι κωδικός που μπήκε κατά λάθος στο πεδίο username.
        log_event(conn, now, AuthEvent.LOGIN_FAIL, username=None, detail="unknown_user")
        conn.commit()
        raise InvalidCredentialsError

    if not row["is_active"]:
        verify_password(password, row["password_hash"])
        log_event(
            conn,
            now,
            AuthEvent.LOGIN_FAIL,
            username=name,
            target_user_id=row["id"],
            detail="inactive",
        )
        conn.commit()
        raise InvalidCredentialsError

    if row["locked_until"] is not None and now < _parse(row["locked_until"]):
        verify_password(password, row["password_hash"])
        log_event(conn, now, AuthEvent.LOGIN_LOCKED, username=name, target_user_id=row["id"])
        conn.commit()
        raise InvalidCredentialsError

    if not verify_password(password, row["password_hash"]):
        attempts = row["failed_attempts"] + 1
        log_event(
            conn,
            now,
            AuthEvent.LOGIN_FAIL,
            username=name,
            target_user_id=row["id"],
            detail="bad_password",
        )
        if attempts >= LOCKOUT_THRESHOLD:
            conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = ?, updated_at = ? WHERE id = ?",
                (iso(now + LOCKOUT_DURATION), iso(now), row["id"]),
            )
            log_event(conn, now, AuthEvent.LOCKOUT, username=name, target_user_id=row["id"])
        else:
            conn.execute(
                "UPDATE users SET failed_attempts = ?, updated_at = ? WHERE id = ?",
                (attempts, iso(now), row["id"]),
            )
        conn.commit()
        raise InvalidCredentialsError

    conn.execute(
        "UPDATE users SET failed_attempts = 0, locked_until = NULL, updated_at = ? WHERE id = ?",
        (iso(now), row["id"]),
    )
    return row


def create_session(
    conn: sqlite3.Connection, user_id: int, username: str, now: datetime, hours: int
) -> str:
    """Επιστρέφει το raw token (μόνο για το cookie). Στη βάση πάει μόνο το sha256."""
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (iso(now),))
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (hash_token(token), user_id, iso(now), iso(now + timedelta(hours=hours))),
    )
    log_event(conn, now, AuthEvent.LOGIN_OK, username=username, target_user_id=user_id)
    conn.commit()
    return token


def lookup_session(conn: sqlite3.Connection, token: str, now: datetime) -> SessionRecord | None:
    token_hash = hash_token(token)
    row = conn.execute(
        """
        SELECT s.token_hash, s.expires_at, u.id, u.username, u.role, u.is_active, u.must_change_pw
        FROM sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ?
        """,
        (token_hash,),
    ).fetchone()
    if row is None:
        return None
    if now >= _parse(row["expires_at"]):
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        conn.commit()
        return None
    if not row["is_active"]:
        return None
    return SessionRecord(
        token_hash=row["token_hash"],
        user_id=row["id"],
        username=row["username"],
        role=row["role"],
        must_change_pw=bool(row["must_change_pw"]),
    )


def end_session(conn: sqlite3.Connection, session: SessionRecord, now: datetime) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (session.token_hash,))
    log_event(
        conn, now, AuthEvent.LOGOUT, username=session.username, target_user_id=session.user_id
    )
    conn.commit()


def discard_session_token(conn: sqlite3.Connection, token: str) -> None:
    """Σβήνει ένα (πιθανώς παλιό) session χωρίς log, π.χ. στο νέο login."""
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))


def change_password(
    conn: sqlite3.Connection,
    session: SessionRecord,
    current_password: str,
    new_password: str,
    now: datetime,
) -> None:
    row = conn.execute(
        "SELECT password_hash FROM users WHERE id = ?", (session.user_id,)
    ).fetchone()
    if row is None or not verify_password(current_password, row["password_hash"]):
        raise InvalidCredentialsError
    check_password_policy(new_password)
    if new_password == current_password:
        raise PasswordPolicyError("Ο νέος κωδικός πρέπει να διαφέρει από τον τρέχοντα.")
    conn.execute(
        "UPDATE users SET password_hash = ?, must_change_pw = 0, updated_at = ? WHERE id = ?",
        (hash_password(new_password), iso(now), session.user_id),
    )
    # Τα υπόλοιπα sessions του χρήστη (π.χ. σε άλλη συσκευή) ακυρώνονται.
    conn.execute(
        "DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
        (session.user_id, session.token_hash),
    )
    log_event(
        conn,
        now,
        AuthEvent.PASSWORD_CHANGE,
        username=session.username,
        target_user_id=session.user_id,
    )
    conn.commit()


# --- διαχείριση χρηστών -------------------------------------------------------


def create_user(
    conn: sqlite3.Connection,
    username: str,
    role: str,
    password: str,
    must_change_pw: bool,
    now: datetime,
    actor_user_id: int | None,
    event: AuthEvent,
) -> int:
    name = normalize_username(username)
    if not USERNAME_RE.match(name):
        raise UsernameError("Το username πρέπει να έχει 3-64 χαρακτήρες: a-z, 0-9, '.', '_', '-'.")
    if role not in ROLES:
        raise ValueError(f"Άγνωστος ρόλος: {role}")
    try:
        cursor = conn.execute(
            """
            INSERT INTO users (username, password_hash, role, must_change_pw, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, hash_password(password), role, int(must_change_pw), iso(now), iso(now)),
        )
    except sqlite3.IntegrityError as exc:
        raise UsernameError("Το username υπάρχει ήδη.") from exc
    user_id = cursor.lastrowid
    log_event(conn, now, event, username=name, actor_user_id=actor_user_id, target_user_id=user_id)
    conn.commit()
    return user_id


def create_user_with_temp_password(
    conn: sqlite3.Connection, username: str, role: str, actor_user_id: int, now: datetime
) -> tuple[int, str, str]:
    """Επιστρέφει (id, κανονικοποιημένο username, προσωρινός κωδικός)."""
    temp = generate_temp_password()
    user_id = create_user(
        conn, username, role, temp, True, now, actor_user_id, AuthEvent.ADMIN_CREATE_USER
    )
    return user_id, normalize_username(username), temp


def list_users(conn: sqlite3.Connection, now: datetime) -> list[dict]:
    rows = conn.execute(
        "SELECT id, username, role, is_active, must_change_pw, locked_until, created_at FROM users ORDER BY username"
    ).fetchall()
    return [
        {
            "id": r["id"],
            "username": r["username"],
            "role": r["role"],
            "is_active": bool(r["is_active"]),
            "must_change_pw": bool(r["must_change_pw"]),
            "locked": r["locked_until"] is not None and now < _parse(r["locked_until"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def _get_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Ο χρήστης {user_id} δεν βρέθηκε.")
    return row


def disable_user(
    conn: sqlite3.Connection, target_user_id: int, actor_user_id: int, now: datetime
) -> None:
    target = _get_user(conn, target_user_id)
    # Ένα statement: ο έλεγχος "τελευταίος ενεργός admin" και η αλλαγή γίνονται
    # ατομικά, χωρίς παράθυρο ανάμεσα σε SELECT και UPDATE.
    cursor = conn.execute(
        """
        UPDATE users SET is_active = 0, updated_at = ?
        WHERE id = ?
          AND NOT (role = 'admin' AND is_active = 1
                   AND (SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1) <= 1)
        """,
        (iso(now), target_user_id),
    )
    if cursor.rowcount == 0:
        conn.rollback()
        raise LastAdminError("Ο τελευταίος ενεργός admin δεν μπορεί να απενεργοποιηθεί.")
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (target_user_id,))
    log_event(
        conn,
        now,
        AuthEvent.ADMIN_DISABLE_USER,
        username=target["username"],
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
    )
    conn.commit()


def reset_password(
    conn: sqlite3.Connection, target_user_id: int, actor_user_id: int, now: datetime
) -> str:
    target = _get_user(conn, target_user_id)
    temp = generate_temp_password()
    conn.execute(
        """
        UPDATE users
        SET password_hash = ?, must_change_pw = 1, failed_attempts = 0, locked_until = NULL, updated_at = ?
        WHERE id = ?
        """,
        (hash_password(temp), iso(now), target_user_id),
    )
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (target_user_id,))
    log_event(
        conn,
        now,
        AuthEvent.ADMIN_RESET_PASSWORD,
        username=target["username"],
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
    )
    conn.commit()
    return temp
