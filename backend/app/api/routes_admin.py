"""Διαχείριση χρηστών: /api/admin/* (μόνο admin, βλ. include_router στο
app.api.main). Οι προσωρινοί κωδικοί επιστρέφονται μία φορά στην απάντηση
και δεν γράφονται ποτέ σε log, auth_log ή βάση (μόνο το scrypt hash τους)."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_db
from app.api.schemas import CreatedUserResponse, CreateUserRequest, TempPasswordResponse, UserOut
from app.auth import service
from app.auth.deps import Clock, SessionUser, get_clock, require_admin

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}


@router.get("/users", response_model=list[UserOut])
def list_users(
    conn: sqlite3.Connection = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> list[UserOut]:
    return [UserOut(**u) for u in service.list_users(conn, clock())]


@router.post("/users", response_model=CreatedUserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    response: Response,
    admin: SessionUser = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> CreatedUserResponse:
    try:
        user_id, username, temp = service.create_user_with_temp_password(
            conn, body.username, body.role, admin.id, clock()
        )
    except service.UsernameError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    response.headers.update(_NO_STORE)
    return CreatedUserResponse(id=user_id, username=username, role=body.role, temp_password=temp)


@router.post("/users/{user_id}/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable_user(
    user_id: int,
    admin: SessionUser = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Response:
    try:
        service.disable_user(conn, user_id, admin.id, clock())
    except service.LastAdminError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/reset-password", response_model=TempPasswordResponse)
def reset_password(
    user_id: int,
    response: Response,
    admin: SessionUser = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> TempPasswordResponse:
    temp = service.reset_password(conn, user_id, admin.id, clock())
    response.headers.update(_NO_STORE)
    return TempPasswordResponse(temp_password=temp)
