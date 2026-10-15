"""Logs χωρίς περιεχόμενο: καμία εξαίρεση δεν γράφει μήνυμα, locals ή traceback.

Στο ailab26 τα .out/.err των jobs τα διαβάζει κάθε χρήστης του portal, άρα
ό,τι φτάνει στο stderr θεωρείται δημόσιο. Τα μηνύματα εξαιρέσεων μπορεί να
περιέχουν person_id, ονόματα ή κείμενο ερώτησης, οπότε στο log πάει ΜΟΝΟ ο
τύπος της εξαίρεσης και το αρχείο:γραμμή του βαθύτερου frame μέσα στο
backend/app.

- SafeErrorMiddleware: πιάνει κάθε μη αναμενόμενη εξαίρεση, απαντά 500 με
  γενικό σώμα και ΔΕΝ την ξαναπετά. Έτσι ούτε το ServerErrorMiddleware του
  Starlette ούτε το uvicorn ("Exception in ASGI application") βλέπουν ποτέ
  την εξαίρεση.
- install_log_redaction: δεύτερη γραμμή άμυνας. LogRecord factory που αφαιρεί
  exc_info/stack_info από ΚΑΘΕ record, όποιος logger ή handler κι αν το
  γράψει (και handlers που προστίθενται αργότερα, και το logging.lastResort).
  Κάνει chain στο προηγούμενο factory και δεν τυλίγει τον εαυτό του δεύτερη
  φορά."""

import logging
import os
from pathlib import Path
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

APP_DIR = Path(__file__).resolve().parents[1]  # backend/app
# Τα frames αυτού του αρχείου (το middleware) δεν είναι "το σημείο όπου έγινε".
_THIS_FILE = os.path.normcase(os.path.abspath(__file__))

logger = logging.getLogger("app.errors")

_REDACTION_MARKER = "_evalassist_log_redaction"


def _app_relative(filename: str) -> str | None:
    """'app/x/y.py' αν το αρχείο είναι κάτω από το backend/app, αλλιώς None."""
    try:
        path = os.path.normcase(os.path.abspath(filename))
        if path == _THIS_FILE:
            return None
        root = os.path.normcase(str(APP_DIR))
        if os.path.commonpath([path, root]) != root:
            return None
    except ValueError:  # διαφορετικός δίσκος στα Windows
        return None
    return "app/" + Path(os.path.relpath(path, root)).as_posix()


def exception_location(exc: BaseException) -> str:
    """'<module.Type> at app/x/y.py:N' από το βαθύτερο frame μέσα στο
    backend/app. Δεν διαβάζει ποτέ str(exc), args ή locals."""
    exc_type = type(exc)
    name = f"{exc_type.__module__}.{exc_type.__qualname__}"
    where = "<external>"
    tb = exc.__traceback__
    while tb is not None:
        relative = _app_relative(tb.tb_frame.f_code.co_filename)
        if relative is not None:
            where = f"{relative}:{tb.tb_lineno}"
        tb = tb.tb_next
    return f"{name} at {where}"


class SafeErrorMiddleware:
    """Καθαρό ASGI middleware, το εξωτερικότερο του app (μόνο το
    ServerErrorMiddleware του Starlette είναι πιο έξω, και δεν βλέπει ποτέ
    εξαίρεση). Οι domain exceptions (404/400/422/503) χειρίζονται πιο μέσα
    από τους handlers του app.api.main και δεν φτάνουν εδώ."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def _send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception as exc:
            logger.error("Unhandled %s", exception_location(exc))
            if response_started:
                # Τα headers έχουν ήδη σταλεί: δεν υπάρχει τρόπος για 500.
                return
            response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
            await response(scope, receive, send)


def _redact(record: logging.LogRecord) -> logging.LogRecord:
    if record.exc_info:
        exc = record.exc_info[1]
        summary = exception_location(exc) if exc is not None else "exception"
        # Το summary δεν έχει '%', αλλά το msg μπορεί να μορφοποιηθεί με args.
        record.msg = f"{record.msg} [{summary.replace('%', '%%')}]"
    record.exc_info = None
    record.exc_text = None
    record.stack_info = None
    return record


def install_log_redaction() -> None:
    """Idempotent: αν το τρέχον factory είναι ήδη το δικό μας, δεν κάνει τίποτα."""
    previous = logging.getLogRecordFactory()
    if getattr(previous, _REDACTION_MARKER, False):
        return

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        return _redact(previous(*args, **kwargs))

    setattr(factory, _REDACTION_MARKER, True)
    logging.setLogRecordFactory(factory)
