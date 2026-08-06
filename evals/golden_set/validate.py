"""Validate a golden set JSONL file.

Checks JSON validity, mixed-script tokens (Latin homoglyphs inside Greek
words, the same failure class handled at ingestion by homoglyphs.py), and
that any forbidden_patterns compile as regexes.

Usage: python evals/golden_set/validate.py <path.jsonl>
"""

import json
import re
import sys


def is_mixed_script(token: str) -> bool:
    has_latin = any(0x41 <= ord(c) <= 0x7A and c.isalpha() for c in token)
    has_greek = any(0x370 <= ord(c) <= 0x3FF for c in token)
    letters = [c for c in token if c.isalpha()]
    if not (has_latin and has_greek and letters):
        return False
    greek_letters = sum(1 for c in letters if 0x370 <= ord(c) <= 0x3FF)
    return greek_letters > len(letters) / 2


def main(path: str) -> int:
    bad = 0
    seen_ids = set()
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"LINE {i} JSON ERROR: {exc}")
                bad += 1
                continue

            # Only text that gets compared against document content is checked
            # for homoglyphs. forbidden_patterns are regexes: their \d and \s
            # escapes are Latin by design and are validated by re.compile below.
            checked = [obj.get("question", "")]
            for key in ("must_include", "must_not_include"):
                checked.extend(obj.get("expected", {}).get(key, []))
            for value in checked:
                for token in re.findall(r"\S+", value):
                    if is_mixed_script(token):
                        print(f"LINE {i} MIXED SCRIPT: {token!r}")
                        bad += 1

            qid = obj.get("id")
            if qid in seen_ids:
                print(f"LINE {i} DUPLICATE ID: {qid}")
                bad += 1
            seen_ids.add(qid)

            expected = obj.get("expected", {})
            for pattern in expected.get("forbidden_patterns", []):
                try:
                    re.compile(pattern)
                except re.error as exc:
                    print(f"LINE {i} BAD REGEX {pattern!r}: {exc}")
                    bad += 1

            if obj.get("tier") == "C" and not obj.get("notes", "").strip():
                print(f"LINE {i} TIER C WITHOUT NOTES: {qid}")
                bad += 1

            print(f"LINE {i} OK id={qid} tier={obj.get('tier')} kind={expected.get('kind')}")

    print("BAD:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
