"""File-based, versioned prompt loading.

Prompts ζουν ως αρχεία σε backend/app/prompts/<name>/vN.txt. Η ανάλυση του
"latest" είναι ντετερμινιστική: μέγιστο N ανάμεσα στα διαθέσιμα vN.txt
αρχεία ενός prompt directory — όχι mtime, όχι σειρά λίστας φακέλου.
"""

import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

_VERSION_FILE_RE = re.compile(r"^v(\d+)\.txt$")
_VERSION_ARG_RE = re.compile(r"^v(\d+)$")


class PromptNotFoundError(Exception):
    """Το prompt name ή η ζητούμενη version δεν βρέθηκαν στο prompts/ directory."""


def _available_versions(name: str) -> dict[int, Path]:
    prompt_dir = PROMPTS_DIR / name
    if not prompt_dir.is_dir():
        raise PromptNotFoundError(f"Άγνωστο prompt '{name}': {prompt_dir} δεν υπάρχει")
    versions: dict[int, Path] = {}
    for path in prompt_dir.glob("v*.txt"):
        match = _VERSION_FILE_RE.match(path.name)
        if match:
            versions[int(match.group(1))] = path
    if not versions:
        raise PromptNotFoundError(f"Δεν βρέθηκαν vN.txt αρχεία για prompt '{name}' σε {prompt_dir}")
    return versions


def load_prompt(name: str, version: str = "latest") -> tuple[str, str]:
    """Επιστρέφει (κείμενο, ανεπτυγμένη έκδοση π.χ. 'v1')."""
    versions = _available_versions(name)
    if version == "latest":
        resolved = max(versions)
    else:
        match = _VERSION_ARG_RE.match(version)
        if not match:
            raise PromptNotFoundError(f"Μη έγκυρη μορφή version '{version}' (αναμένεται 'vN' ή 'latest')")
        resolved = int(match.group(1))
        if resolved not in versions:
            raise PromptNotFoundError(f"Prompt '{name}' δεν έχει έκδοση v{resolved}")
    text = versions[resolved].read_text(encoding="utf-8")
    return text, f"v{resolved}"
