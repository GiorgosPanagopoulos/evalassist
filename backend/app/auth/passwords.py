"""Hashing κωδικών με hashlib.scrypt (stdlib, καμία νέα εξάρτηση).

Μορφή αποθήκευσης: 'scrypt$n$r$p$salt_hex$hash_hex'. Οι παράμετροι
αποθηκεύονται μαζί με το hash, ώστε μια μελλοντική αύξηση του n να μη
σπάει τους υπάρχοντες κωδικούς."""

import hashlib
import hmac
import secrets
from functools import lru_cache

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
_DKLEN = 64
MIN_PASSWORD_LENGTH = 12


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=_DKLEN)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    derived = _derive(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        derived = _derive(password, salt, int(n), int(r), int(p))
    except ValueError:
        return False
    return hmac.compare_digest(derived, expected)


@lru_cache
def _dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(32))


def dummy_verify(password: str) -> None:
    """Ίδιο κόστος scrypt με ένα πραγματικό verify, για άγνωστο χρήστη: ο
    χρόνος απόκρισης δεν αποκαλύπτει αν το username υπάρχει."""
    verify_password(password, _dummy_hash())


def generate_temp_password() -> str:
    """Προσωρινός κωδικός (16 χαρακτήρες) για νέο χρήστη ή reset. Επιστρέφεται
    μία φορά στον admin, δεν γράφεται ποτέ σε log ή στη βάση."""
    return secrets.token_urlsafe(12)
