"""Έλεγχος μετά την εγκατάσταση, χωρίς browser και χωρίς portal.

Τρέχει μόνο με την stdlib της Python. Ελέγχει με τη σειρά: health, login,
/api/auth/me (semantic κλειστό), μία δομημένη ερώτηση, semantic -> 403,
logout και ότι το session έληξε.

Το session cookie είναι Secure, άρα σε http://127.0.0.1 κανένα cookie jar δεν
το ξαναστέλνει. Το script διαβάζει το Set-Cookie του login και το στέλνει
ρητά ως header Cookie. Η τιμή του cookie και ο κωδικός δεν τυπώνονται ποτέ.
Username, person_id και περίοδος ζητούνται interactively, ο κωδικός με
getpass, ώστε τίποτα να μη μείνει στο ιστορικό του shell. Από τις απαντήσεις
τυπώνονται μόνο status codes και πλήθη, όχι δεδομένα.

Χρήση (στον server, με το venv του backend):
    python deploy/smoke_test.py http://127.0.0.1:<PORT>
Exit 0 αν όλοι οι έλεγχοι πέρασαν, αλλιώς 1.

Οι κλήσεις γράφουν κανονικά στο audit_log και στο auth_log, όπως κάθε χρήση.
"""

import getpass
import json
import sys
import urllib.error
import urllib.request
from typing import Callable


class Response:
    def __init__(self, status: int, headers, body: bytes):
        self.status = status
        self.headers = headers
        self.body = body

    def json(self):
        try:
            return json.loads(self.body.decode("utf-8"))
        except ValueError:
            return None


def _request(url: str, method: str = "GET", payload: dict | None = None, cookie: str | None = None) -> Response:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if cookie:
        request.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return Response(response.status, response.headers, response.read())
    except urllib.error.HTTPError as exc:
        return Response(exc.code, exc.headers, exc.read())


def cookie_header(set_cookie_headers: list[str]) -> str:
    """Από τα Set-Cookie κρατά μόνο τα name=value (χωρίς Path, Secure κ.λπ.),
    έτοιμα για header Cookie."""
    pairs = [header.split(";", 1)[0].strip() for header in set_cookie_headers]
    return "; ".join(pair for pair in pairs if "=" in pair)


def cookie_attributes(set_cookie_headers: list[str]) -> str:
    """Μόνο τα attributes (όχι η τιμή), για να φαίνεται ότι είναι Secure/HttpOnly."""
    found = set()
    path = None
    for header in set_cookie_headers:
        for part in header.split(";")[1:]:
            name, _, value = part.strip().partition("=")
            lowered = name.lower()
            if lowered in ("secure", "httponly"):
                found.add(name)
            elif lowered == "samesite":
                found.add(f"SameSite={value}")
            elif lowered == "path":
                path = value
    attributes = sorted(found)
    if path is not None:
        attributes.append(f"Path={path}")
    return ", ".join(attributes)


def main(
    base_url: str,
    input_fn: Callable[[str], str] = input,
    getpass_fn: Callable[[str], str] = getpass.getpass,
    out: Callable[[str], None] = print,
) -> int:
    base = base_url.rstrip("/")
    failures = 0

    def check(ok: bool, label: str, detail: str = "") -> bool:
        nonlocal failures
        if not ok:
            failures += 1
        out(f"{'OK  ' if ok else 'FAIL'} {label}" + (f" ({detail})" if detail else ""))
        return ok

    health = _request(f"{base}/api/health")
    body = health.json() or {}
    check(health.status == 200 and body.get("status") == "ok", "health", f"HTTP {health.status}")
    if health.status == 200:
        out(f"     ollama_reachable={body.get('ollama_reachable')} "
            "(false είναι αναμενόμενο με το semantic κλειστό)")

    username = input_fn("Username: ").strip()
    password = getpass_fn("Κωδικός: ")
    login = _request(f"{base}/api/auth/login", "POST", {"username": username, "password": password})
    del password
    set_cookies = (login.headers.get_all("Set-Cookie") if login.headers else None) or []
    cookie = cookie_header(set_cookies)
    if not check(login.status == 200 and bool(cookie), "login", f"HTTP {login.status}"):
        out("     Τα υπόλοιπα βήματα χρειάζονται session. Τέλος.")
        return 1
    out(f"     cookie attributes: {cookie_attributes(set_cookies)}")
    if (login.json() or {}).get("must_change_pw"):
        out("     Ο χρήστης πρέπει να αλλάξει κωδικό: τα endpoints δεδομένων θα δώσουν 403.")

    me = _request(f"{base}/api/auth/me", cookie=cookie)
    features = (me.json() or {}).get("features") or {}
    check(
        me.status == 200 and features.get("semantic_enabled") is False,
        "me, semantic_enabled=false",
        f"HTTP {me.status}",
    )

    person_id = input_fn("person_id για τη δομημένη ερώτηση: ").strip()
    period = input_fn("Περίοδος (YYYY-MM-DD..YYYY-MM-DD): ").strip()

    structured = _request(
        f"{base}/api/query/structured",
        "POST",
        {"person_id": person_id, "period": period, "operation": "get_scores"},
        cookie=cookie,
    )
    result = (structured.json() or {}).get("result") or {}
    check(
        structured.status == 200 and "data" in result,
        "δομημένη ερώτηση (get_scores)",
        f"HTTP {structured.status}, {len(result.get('retrieved_doc_ids') or [])} έγγραφα",
    )

    semantic = _request(
        f"{base}/api/query/semantic",
        "POST",
        {"person_id": person_id, "period": period, "question": "Έλεγχος εγκατάστασης"},
        cookie=cookie,
    )
    check(
        semantic.status == 403 and (semantic.json() or {}).get("code") == "semantic_disabled",
        "semantic κλειστό (403 semantic_disabled)",
        f"HTTP {semantic.status}",
    )

    logout = _request(f"{base}/api/auth/logout", "POST", cookie=cookie)
    check(logout.status == 204, "logout", f"HTTP {logout.status}")
    after = _request(f"{base}/api/auth/me", cookie=cookie)
    check(after.status == 401, "το session έληξε μετά το logout", f"HTTP {after.status}")

    out("Όλοι οι έλεγχοι πέρασαν." if failures == 0 else f"{failures} έλεγχοι απέτυχαν.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Χρήση: python deploy/smoke_test.py http://127.0.0.1:<PORT>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
