"""Golden set runner for EvalAssist.

Standalone script, not pytest (pytest is not installed in this repo).
Spec: private/prompts/eval_runner.md, eval_runner_amend.md, eval_runner_amend2.md.

Usage:
python evals/runner/run_golden_set.py --questions private/golden_set/questions.jsonl --base-url http://127.0.0.1:8000 --tier A
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import httpx

# get_promotions_table / get_service_time_table are career-wide: the API
# ignores request.period for these operations and always uses CAREER_PERIOD
# internally (see backend/app/api/routes_query.py). This fixed value is what
# the runner sends anyway, since the request schema requires a period string.
# Known open item, not hidden: see period_ignored_by_operation in the output.
CAREER_WIDE_PERIOD_SENT = "2024-01-01..2024-07-02"

# Fixed inside the runner, not the golden set. Each entry maps a Tier A
# question id to the structured operation and the path extraction into
# result.data. None means the question requires multi-call aggregation the
# runner does not do, and is reported as NOT_IMPLEMENTED, not FAIL.
TIER_A_MAP = {
    "A-01": None,
    "A-02": {"operation": "get_promotions_table", "extract": lambda d: len(d["rows"]), "career_wide": True},
    "A-03": {"operation": "get_scores", "extract": lambda d: d["characterization"], "career_wide": False},
    "A-04": {"operation": "get_scores", "extract": lambda d: d["score"], "career_wide": False},
    "A-05": None,
    "A-06": None,
    "A-07": None,
    "A-08": None,
    "A-09": {"operation": "get_scores", "extract": lambda d: d["field_scores"], "career_wide": False},
    "A-10": {"operation": "get_service_time_table", "extract": lambda d: d["rows"], "career_wide": True},
}

ALL_STATUSES = ["PASS", "FAIL", "NOT_IMPLEMENTED", "ERROR", "KNOWN_GAP", "MANUAL_REVIEW"]


def load_questions(path):
    questions = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            questions.append(json.loads(line))
    return questions


def preflight_validate(questions):
    errors = []
    for q in questions:
        if q["tier"] == "A" and q["id"] not in TIER_A_MAP:
            errors.append(f"{q['id']}: Tier A question not mapped in TIER_A_MAP")
        if q["tier"] in ("B", "C") and q.get("period") is None:
            errors.append(f"{q['id']}: Tier {q['tier']} question has period=null")
    return errors


def compare_exact(expected_value, actual_value):
    return expected_value == actual_value


def compare_set(expected_values, actual_value):
    dumped = json.dumps(actual_value, ensure_ascii=False)
    ok = all(v in dumped for v in expected_values)
    weak = any(len(v) < 3 for v in expected_values)
    return ok, weak


def compare_contains(must_include, must_not_include, text):
    missing = [v for v in must_include if v not in text]
    present = [v for v in must_not_include if v in text]
    return (not missing and not present), missing, present


def check_forbidden_patterns(patterns, text):
    return [p for p in patterns if re.search(p, text)]


def run_tier_a(client, base_url, q, check_routing, timeout):
    row = {
        "id": q["id"],
        "tier": "A",
        "mode": q["mode"],
        "question": q["question"],
        "person_id": q["person_id"],
        "notes": q.get("notes", ""),
    }
    mapping = TIER_A_MAP[q["id"]]

    if mapping is None:
        row["status"] = "NOT_IMPLEMENTED"
        row["operation"] = None
    else:
        period_sent = CAREER_WIDE_PERIOD_SENT if mapping["career_wide"] else q["period"]
        row["operation"] = mapping["operation"]
        row["period_sent"] = period_sent
        if mapping["career_wide"]:
            row["period_ignored_by_operation"] = True
        payload = {"person_id": q["person_id"], "period": period_sent, "operation": mapping["operation"]}
        try:
            resp = client.post(f"{base_url}/query/structured", json=payload, timeout=timeout)
        except httpx.HTTPError as exc:
            row["status"] = "ERROR"
            row["error"] = str(exc)
            return _apply_check_routing(client, base_url, q, check_routing, row, timeout)

        row["http_status"] = resp.status_code
        if resp.status_code >= 400:
            row["status"] = "ERROR"
            row["error_body"] = resp.text
            return _apply_check_routing(client, base_url, q, check_routing, row, timeout)

        raw = resp.json()
        row["raw_response"] = raw
        data = raw["result"]["data"]
        try:
            value_at_path = mapping["extract"](data)
        except (KeyError, TypeError) as exc:
            row["status"] = "ERROR"
            row["error"] = f"path extraction failed: {exc}"
            return _apply_check_routing(client, base_url, q, check_routing, row, timeout)

        row["value_at_path"] = value_at_path
        expected = q["expected"]
        row["expected"] = expected
        if expected["kind"] == "exact":
            ok = compare_exact(expected["value"], value_at_path)
            row["status"] = "PASS" if ok else "FAIL"
        elif expected["kind"] == "set":
            ok, weak = compare_set(expected["values"], value_at_path)
            row["status"] = "PASS" if ok else "FAIL"
            row["weak_match"] = weak
        else:
            row["status"] = "ERROR"
            row["error"] = f"unsupported expected kind for Tier A: {expected['kind']}"

    return _apply_check_routing(client, base_url, q, check_routing, row, timeout)


def _apply_check_routing(client, base_url, q, check_routing, row, timeout):
    if not check_routing:
        return row
    period = q.get("period")
    if period is None:
        # route_query(question) only looks at the question text, so the
        # period value in this request is a technical filler to satisfy the
        # request schema, not a claim about the question. "career" is a
        # valid, isolation-safe CAREER_PERIOD value.
        period = "career"
        row["routing_period_substituted"] = True
    payload = {"person_id": q["person_id"], "period": period, "question": q["question"]}
    try:
        resp = client.post(f"{base_url}/query/semantic", json=payload, timeout=timeout)
    except httpx.HTTPError as exc:
        row["routing_check"] = f"ERROR {exc}"
        return row
    if resp.status_code >= 400:
        row["routing_check"] = f"ERROR {resp.status_code}"
        return row
    row["routing_hint"] = resp.json()["result"].get("routing_hint")
    return row


def _run_semantic(client, base_url, q, tier, csv_rows, timeout):
    row = {
        "id": q["id"],
        "tier": tier,
        "mode": q["mode"],
        "question": q["question"],
        "person_id": q["person_id"],
        "period_sent": q["period"],
        "notes": q.get("notes", ""),
    }
    if tier == "B":
        row["known_data_gap"] = bool(q.get("known_data_gap", False))

    payload = {"person_id": q["person_id"], "period": q["period"], "question": q["question"]}
    try:
        resp = client.post(f"{base_url}/query/semantic", json=payload, timeout=timeout)
    except httpx.HTTPError as exc:
        row["status"] = "ERROR"
        row["error"] = str(exc)
        return row

    row["http_status"] = resp.status_code
    if resp.status_code >= 400:
        row["status"] = "ERROR"
        row["error_body"] = resp.text
        return row

    raw = resp.json()
    row["raw_response"] = raw
    result = raw["result"]
    row["answer"] = result["answer"]
    row["citations"] = result["citations"]
    row["prompt_version"] = result.get("prompt_version")
    row["unsupported_ranks"] = result.get("unsupported_ranks", [])
    row["routing_hint"] = result.get("routing_hint")

    for rank, cit in enumerate(result["citations"], start=1):
        csv_rows.append([q["id"], tier, rank, cit["doc_id"], cit["section"], cit["score"]])

    expected = q["expected"]
    row["expected"] = expected

    if tier == "B":
        kind = expected.get("kind")
        if kind == "contains":
            ok, missing, present = compare_contains(
                expected.get("must_include", []), expected.get("must_not_include", []), result["answer"]
            )
            row["missing_must_include"] = missing
            row["present_must_not_include"] = present
        elif kind == "exact":
            ok = compare_exact(expected["value"], result["answer"])
        elif kind == "set":
            ok, weak = compare_set(expected["values"], result["answer"])
            row["weak_match"] = weak
        else:
            row["status"] = "ERROR"
            row["error"] = f"unsupported expected kind for Tier B: {kind}"
            return row

        forbidden = expected.get("forbidden_patterns", [])
        if forbidden:
            matched = check_forbidden_patterns(forbidden, result["answer"])
            if matched:
                ok = False
                row["forbidden_pattern_matched"] = matched
        row["status"] = "KNOWN_GAP" if row["known_data_gap"] else ("PASS" if ok else "FAIL")
    else:  # Tier C: warning only, never a verdict
        row["forbidden_pattern_matched"] = check_forbidden_patterns(expected.get("forbidden_patterns", []), result["answer"])
        row["status"] = "MANUAL_REVIEW"

    return row


def write_summary(path, rows, args, timestamp):
    lines = [
        f"# Golden set run {timestamp}",
        "",
        f"base_url: {args.base_url}",
        f"tier filter: {args.tier}",
        f"check_routing: {args.check_routing}",
        f"timeout: {args.timeout}",
        "",
        "NOT_IMPLEMENTED and KNOWN_GAP are never merged into PASS/FAIL. Tier C rows are MANUAL_REVIEW, never PASS/FAIL.",
        "",
        "| tier | " + " | ".join(ALL_STATUSES) + " | total |",
        "|---|" + "---|" * (len(ALL_STATUSES) + 1),
    ]
    for tier in ("A", "B", "C"):
        tier_rows = [r for r in rows if r["tier"] == tier]
        if not tier_rows:
            continue
        counts = [str(sum(1 for r in tier_rows if r["status"] == s)) for s in ALL_STATUSES]
        lines.append(f"| {tier} | " + " | ".join(counts) + f" | {len(tier_rows)} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_rerank_csv(path, csv_rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["question_id", "tier", "rank_position", "doc_id", "section", "score"])
        writer.writerows(csv_rows)


def write_manual_review(path, rows):
    review_rows = [r for r in rows if r["tier"] == "C" or r.get("known_data_gap")]
    lines = [
        "# Tier C manual review",
        "",
        "Tier C ερωτησεις και οι Tier B ερωτησεις με known_data_gap (B-11, B-12).",
        "",
    ]
    for r in review_rows:
        lines.append(f"## {r['id']} ({r['tier']})")
        lines.append("")
        lines.append(f"Ερωτηση: {r['question']}")
        lines.append("")
        lines.append(f"Status: {r['status']}")
        lines.append("")
        if r["status"] == "ERROR":
            lines.append(f"ERROR: {r.get('error') or r.get('error_body')}")
            lines.append("")
        else:
            lines.append("Απαντηση:")
            lines.append("")
            lines.append(r.get("answer", ""))
            lines.append("")
            matched = r.get("forbidden_pattern_matched")
            if matched:
                lines.append(f"forbidden_patterns matched (προειδοποιηση μονο, οχι verdict): {matched}")
                lines.append("")
        lines.append("ΧΑΡΑΚΤΗΡΙΣΜΟΣ (συμπληρωνεται απο ανθρωπο):")
        lines.append("")
        lines.append("[ ] ΣΩΣΤΗ ΑΡΝΗΣΗ")
        lines.append("[ ] ΕΥΛΟΓΟΣ ΣΥΜΠΕΡΑΣΜΟΣ (η απαντηση προκυπτει απο το context, αλλα οχι ρητα)")
        lines.append("[ ] ΠΑΡΑΙΣΘΗΣΗ")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Golden set runner")
    parser.add_argument("--questions", default="private/golden_set/questions.jsonl")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--tier", default="all", choices=["A", "B", "C", "all"])
    parser.add_argument("--check-routing", action="store_true", default=False)
    parser.add_argument("--out", default="private/golden_set/results/")
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    questions = load_questions(args.questions)
    if args.tier != "all":
        questions = [q for q in questions if q["tier"] == args.tier]

    errors = preflight_validate(questions)
    if errors:
        for e in errors:
            print(f"STOP: {e}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    rows = []
    csv_rows = []
    with httpx.Client() as client:
        for q in questions:
            if q["tier"] == "A":
                row = run_tier_a(client, args.base_url, q, args.check_routing, args.timeout)
            else:
                row = _run_semantic(client, args.base_url, q, q["tier"], csv_rows, args.timeout)
            rows.append(row)

    results_path = out_dir / f"results_{timestamp}.jsonl"
    with open(results_path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    write_summary(out_dir / "summary.md", rows, args, timestamp)
    write_rerank_csv(out_dir / "rerank_scores.csv", csv_rows)
    write_manual_review(out_dir / "tier_c_manual_review.md", rows)

    print(f"Results: {results_path}")
    print(f"Summary: {out_dir / 'summary.md'}")


if __name__ == "__main__":
    main()
