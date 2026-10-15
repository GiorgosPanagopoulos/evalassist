"""Δημιουργία admin από τη γραμμή εντολών (πρώτος admin της εφαρμογής).

Χρήση (από το backend/):
    python -m app.auth.create_admin

Ο κωδικός διαβάζεται ΜΟΝΟ με getpass (δύο φορές), ποτέ ως όρισμα ή από
μεταβλητή περιβάλλοντος, και δεν τυπώνεται ή γράφεται πουθενά. Ο admin που
φτιάχνεται εδώ έχει must_change_pw=0: τον κωδικό τον όρισε ο ίδιος."""

import getpass
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.auth import service
from app.auth.passwords import MIN_PASSWORD_LENGTH
from app.core.config import get_settings
from app.db.database import get_connection, init_db


def main(
    db_path: Path | None = None,
    input_fn: Callable[[str], str] = input,
    getpass_fn: Callable[[str], str] = getpass.getpass,
) -> int:
    db_path = db_path or get_settings().DB_PATH
    init_db(db_path)

    username = service.normalize_username(input_fn("Username admin: "))
    if not service.USERNAME_RE.match(username):
        print("Μη έγκυρο username: 3-64 χαρακτήρες a-z, 0-9, '.', '_', '-'.", file=sys.stderr)
        return 1

    password = getpass_fn("Κωδικός: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(
            f"Ο κωδικός πρέπει να έχει τουλάχιστον {MIN_PASSWORD_LENGTH} χαρακτήρες.",
            file=sys.stderr,
        )
        return 1
    if getpass_fn("Επανάληψη κωδικού: ") != password:
        print("Οι δύο κωδικοί δεν ταιριάζουν.", file=sys.stderr)
        return 1

    conn = get_connection(db_path)
    try:
        service.create_user(
            conn,
            username,
            "admin",
            password,
            must_change_pw=False,
            now=datetime.now(timezone.utc),
            actor_user_id=None,
            event=service.AuthEvent.ADMIN_BOOTSTRAP,
        )
    except service.UsernameError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(f"Δημιουργήθηκε admin '{username}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
