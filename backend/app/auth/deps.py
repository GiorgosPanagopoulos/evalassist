"""FastAPI dependencies για auth.

- get_current_session: έγκυρο session, ακόμη και με must_change_pw=1. Μόνο
  για /api/auth/me, /api/auth/logout, /api/auth/change-password.
- require_user: όπως πάνω, αλλά 403 όσο ισχύει must_change_pw=1. Μπαίνει
  σε όλους τους routers με δεδομένα στο include_router (app.api.main).
- require_admin: require_user + role='admin'.

Ο χρήστης προκύπτει ΜΟΝΟ από το session cookie. Κανένα header δεν
λαμβάνεται υπόψη."""

import sqlite3
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from app.api.deps import get_db
from app.auth import service

SESSION_COOKIE = "evalassist_session"

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_clock() -> Clock:
    """Τα tests κάνουν override με ψεύτικο ρολόι."""
    return _utc_now


class SessionUser(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    username: str
    role: str
    must_change_pw: bool
    token_hash: str

    def as_record(self) -> service.SessionRecord:
        return service.SessionRecord(
            token_hash=self.token_hash,
            user_id=self.id,
            username=self.username,
            role=self.role,
            must_change_pw=self.must_change_pw,
        )


def get_current_session(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> SessionUser:
    token = request.cookies.get(SESSION_COOKIE)
    record = service.lookup_session(conn, token, clock()) if token else None
    if record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Απαιτείται σύνδεση.")
    return SessionUser(
        id=record.user_id,
        username=record.username,
        role=record.role,
        must_change_pw=record.must_change_pw,
        token_hash=record.token_hash,
    )


def require_user(user: SessionUser = Depends(get_current_session)) -> SessionUser:
    if user.must_change_pw:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Απαιτείται αλλαγή κωδικού."
        )
    return user


def require_admin(user: SessionUser = Depends(require_user)) -> SessionUser:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Απαιτείται ρόλος admin.")
    return user
