"""Επαλήθευση της εξαγωγής (parse_pdf -> chunk_by_section -> extract_summary_note)
πάνω σε ΕΝΑ πραγματικό PDF Περιληπτικού Σημειώματος — χωρίς κανένα δεδομένο
hardcoded εδώ (ΚΑΝΕΝΑ όνομα/ΑΓΜ/βαθμολογία στον κώδικα). Το path έρχεται
αποκλειστικά από env var· τυπώνει ΜΟΝΟ counts/keys/booleans, ποτέ τιμές.

Εκτέλεση:
    EVALASSIST_REAL_PDF=private/perilhptiko2018.pdf python scripts/verify_real_pdf.py

Δεν κάνει πλήρες ingestion (SQLite/ChromaDB/embeddings) — μόνο το extraction
pipeline, ώστε να τρέχει γρήγορα και χωρίς εξάρτηση από βαριά ML μοντέλα.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.ingestion.chunker import PageText, chunk_by_section  # noqa: E402
from app.ingestion.extractor import extract_summary_note  # noqa: E402
from app.ingestion.parser import parse_pdf  # noqa: E402


def main() -> int:
    pdf_env = os.environ.get("EVALASSIST_REAL_PDF")
    if not pdf_env:
        print("FAIL  Ορίστε EVALASSIST_REAL_PDF (path στο πραγματικό PDF).", file=sys.stderr)
        return 1
    pdf_path = Path(pdf_env)
    if not pdf_path.is_file():
        print(f"FAIL  Δεν βρέθηκε αρχείο: {pdf_path}", file=sys.stderr)
        return 1

    parsed_pages = parse_pdf(pdf_path)
    pages = [PageText(page=p.page, text=p.text) for p in parsed_pages]
    full_text = "\n".join(p.text for p in pages)

    section_chunks = chunk_by_section(pages, doc_id="verify-real-pdf")
    fallback_used = bool(section_chunks) and section_chunks[0].fallback
    summary_note, raw_texts = extract_summary_note(full_text, section_chunks)

    person = summary_note.person
    entries = summary_note.evaluations

    checks: list[tuple[str, bool]] = []

    checks.append(("person_id (Α.Γ.Μ.) μη κενό", bool(person.agm)))
    checks.append(("name μη κενό", bool(person.name)))
    checks.append(("rank μη κενό", bool(person.rank)))
    checks.append(("corps μη κενό", bool(person.corps)))
    checks.append((f"len(entries) >= 30 (πραγματικό: {len(entries)})", len(entries) >= 30))

    years = sorted({e.period_start.year for e in entries} | {e.period_end.year for e in entries})
    covers_2005_2024 = bool(years) and years[0] <= 2005 and years[-1] >= 2024
    checks.append(
        (f"periods καλύπτουν 2005-2024 (πραγματικό εύρος: {years[0] if years else None}-{years[-1] if years else None})",
         covers_2005_2024)
    )

    entries_with_scores = [e for e in entries if any(isinstance(fs.value, int) for fs in e.field_scores)]
    numeric_scores = [fs.value for e in entries for fs in e.field_scores if isinstance(fs.value, int)]
    scores_in_range = all(0 <= v <= 100 for v in numeric_scores)
    checks.append(
        (f"entries με >=1 αριθμητικό FieldScore >= 4 "
         f"({len(entries_with_scores)}/{len(entries)} entries)",
         len(entries_with_scores) >= 4)
    )
    checks.append(
        (f"κάθε αριθμητικό FieldScore.value στο [0,100] "
         f"({len(numeric_scores)} τιμές ελέγχθηκαν)",
         scores_in_range)
    )

    print("=== Πλήθη/keys (χωρίς πραγματικά δεδομένα) ===")
    print(f"pages: {len(pages)}")
    print(f"fallback_used: {fallback_used}")
    print(f"section_chunks: {len(section_chunks)}")
    print(f"evaluations: {len(entries)}")
    print(f"ea_type counts: Ε.Α.={sum(1 for e in entries if e.ea_type == 'Ε.Α.')}, "
          f"Σ.Α.={sum(1 for e in entries if e.ea_type == 'Σ.Α.')}")
    print(f"period years span: {years[0] if years else None}-{years[-1] if years else None}")
    print(f"entries με >=1 field_score: {len(entries_with_scores)}/{len(entries)}")
    print(f"PersonInfo πεδία που γέμισαν (boolean): "
          f"agm={bool(person.agm)} name={bool(person.name)} father_name={bool(person.father_name)} "
          f"rank={bool(person.rank)} corps={bool(person.corps)} service={bool(person.service)} "
          f"family_status={bool(person.family_status)} age={person.age is not None} "
          f"special_training={bool(person.special_training)}")
    print(f"career sections: promotions={len(summary_note.promotions)}, "
          f"service_time={len(summary_note.service_time)}, degrees={len(summary_note.degrees)}, "
          f"postings={len(summary_note.postings)}, health_entries={len(summary_note.health_entries)}")

    print("\n=== Assertions ===")
    all_ok = True
    for label, ok in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"{status}  {label}")

    print(f"\n{'PASS' if all_ok else 'FAIL'}: verify_real_pdf")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
