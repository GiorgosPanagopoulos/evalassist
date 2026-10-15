"""Auth endpoints: /api/auth/login (δημόσιο), logout, me, change-password.

Το login απαντά ΙΔΙΟ status και body για άγνωστο χρήστη, λάθος κωδικό,
κλειδωμένο ή ανενεργό λογαριασμό (βλ. app.auth.service.authenticate)."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import get_db
from app.api.schemas import ChangePasswordRequest, LoginRequest, MeResponse
from app.auth import service
from app.auth.deps import SESSION_COOKIE, Clock, SessionUser, get_clock, get_current_session
from app.core.config import Settings, get_settings

router = APIRouter()

LOGIN_FAILED_DETAIL = "Λάθος όνομα χρήστη ή κωδικός."


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.SESSION_HOURS * 3600,
        path=settings.COOKIE_PATH,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path=settings.COOKIE_PATH,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


@router.post("/login", response_model=MeResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    conn: sqlite3.Connection = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> MeResponse:
    now = clock()
    try:
        user = service.authenticate(conn, body.username, body.password, now)
    except service.InvalidCredentialsError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=LOGIN_FAILED_DETAIL)
    previous = request.cookies.get(SESSION_COOKIE)
    if previous:
        service.discard_session_token(conn, previous)
    token = service.create_session(conn, user["id"], user["username"], now, settings.SESSION_HOURS)
    _set_session_cookie(response, token, settings)
    return MeResponse(
        id=user["id"],
        username=user["username"],
        role=user["role"],
        must_change_pw=bool(user["must_change_pw"]),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    user: SessionUser = Depends(get_current_session),
    conn: sqlite3.Connection = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> Response:
    service.end_session(conn, user.as_record(), clock())
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookie(response, settings)
    return response


@router.get("/me", response_model=MeResponse)
def me(user: SessionUser = Depends(get_current_session)) -> MeResponse:
    return MeResponse(
        id=user.id, username=user.username, role=user.role, must_change_pw=user.must_change_pw
    )


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest,
    user: SessionUser = Depends(get_current_session),
    conn: sqlite3.Connection = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Response:
    try:
        service.change_password(
            conn, user.as_record(), body.current_password, body.new_password, clock()
        )
    except service.InvalidCredentialsError:
        # 400, όχι 401: το session είναι έγκυρο, λάθος είναι μόνο ο τρέχων κωδικός.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Λάθος τρέχων κωδικός.")
    except service.PasswordPolicyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
