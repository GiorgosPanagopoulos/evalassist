# Extractive spike: Windows runbook

Scripts for the extractive answer spike. This branch is never merged.
Nothing personal lives in these files: the person id, the real questions,
the periods and the expected answers are passed as arguments or kept in
`private\` (gitignored).

Files:

- `verify.py`: quote verification, pure logic (stdlib only).
- `freeze.py`: freezes the retrieval once (bge-m3, Chroma copy, reranker).
- `run.py`: runs one prompt variant against Ollama on the frozen retrieval.
  Imports only the stdlib, `requests` and `verify.py`.
- `variants\E1.txt`, `variants\E2.txt`: system prompts of the two variants.
  V4 is read from `backend\app\prompts\semantic_rag\v4.txt`.
- `questions.example.jsonl`: format of the real `questions.jsonl` (placeholders).
- `test_verify.py`, `test_freeze.py`, `test_run.py`: tests, no pytest.

## Conventions

- Windows PowerShell 5.1. One command per line. Run every line from the repo root.
- All commands use the backend virtualenv interpreter
  `.\backend\.venv\Scripts\python.exe`. Adjust the path if the venv lives elsewhere.
- Check the exit code after each script with `$LASTEXITCODE`. Zero means OK.
- The only environment variable for the spike is `HF_HUB_OFFLINE=1`, and only for `freeze.py`.
  The tests need `PYTHONPATH` set to the repo root while they run.

## 0. Before anything

- The Tier B golden set rerun on plain `main` comes FIRST. It is the baseline the
  spike is compared with, so do not start the spike before it has run and been saved.
- Stop the backend (uvicorn). Ollama must be running.

## 1. Get the branch

Check the network and the working tree first. `git status` must show no local
changes before switching.

```powershell
nslookup github.com
git status
git fetch
git switch spike/extractive
git pull
```

## 2. Write the private inputs by hand

Create the folder:

```powershell
New-Item -ItemType Directory -Force private\scratch\extractive_spike
```

Write these two files by hand:

- `private\scratch\extractive_spike\questions.jsonl`: one line per question,
  same keys as `questions.example.jsonl` (`id`, `question`, `period`).
  Ids: `C4`, `T15`, `C1`, `T17`, `B09`, `T18`. Periods exactly as in the database.
- `private\scratch\extractive_spike\PREREG.md`: the criteria of section 8.4 of the
  design, copied verbatim, plus the expected evaluator for C4.

One way to write `questions.jsonl`: a single-quoted here-string, then
`Set-Content -Encoding utf8`. Replace every placeholder with the real question
and period before running. The `@'` must end its line and the `'@` must start its line.
`Set-Content -Encoding utf8` in PowerShell 5.1 writes a BOM. `freeze.py` accepts it.

```powershell
$questions = @'
{"id": "C4", "question": "<question C4>", "period": "YYYY-MM-DD..YYYY-MM-DD"}
{"id": "T15", "question": "<question T15>", "period": "YYYY-MM-DD..YYYY-MM-DD"}
{"id": "C1", "question": "<question C1>", "period": "YYYY-MM-DD..YYYY-MM-DD"}
{"id": "T17", "question": "<question T17>", "period": "YYYY-MM-DD..YYYY-MM-DD"}
{"id": "B09", "question": "<question B09>", "period": "YYYY-MM-DD..YYYY-MM-DD"}
{"id": "T18", "question": "<question T18>", "period": "YYYY-MM-DD..YYYY-MM-DD"}
'@
Set-Content -Encoding utf8 -Path private\scratch\extractive_spike\questions.jsonl -Value $questions
(Get-Item private\scratch\extractive_spike\questions.jsonl).Length
Get-Content -Encoding utf8 private\scratch\extractive_spike\questions.jsonl
```

The length must be well above 3 bytes (3 bytes is a BOM and nothing else), and
`Get-Content` must show the six lines with the Greek text readable.

Record their hashes before any run:

```powershell
Get-FileHash -Algorithm SHA256 private\scratch\extractive_spike\questions.jsonl
Get-FileHash -Algorithm SHA256 private\scratch\extractive_spike\PREREG.md
```

## 3. Tests (MANDATORY, before any freeze or run)

All three must end with `passed` and no `FAIL`. If any test fails, stop here.

```powershell
$env:PYTHONPATH = "."
.\backend\.venv\Scripts\python.exe evals\spikes\extractive\test_verify.py
.\backend\.venv\Scripts\python.exe evals\spikes\extractive\test_freeze.py
.\backend\.venv\Scripts\python.exe evals\spikes\extractive\test_run.py
Remove-Item Env:PYTHONPATH
```

## 4. Freeze the retrieval

Skip this step if the frozen folder already exists from an earlier run.
`--person-id auto` takes the id from the database, and only works if the database
holds exactly one person. Otherwise pass the exact id; a wrong id stops with exit 1
and prints its codepoints. Every question period must exist in that person's
evaluations (or be `career`), else exit 1 before any model loads.

```powershell
$env:HF_HUB_OFFLINE = "1"
.\backend\.venv\Scripts\python.exe evals\spikes\extractive\freeze.py --person-id auto --questions private\scratch\extractive_spike\questions.jsonl --out private\scratch\extractive_spike\frozen
Remove-Item Env:HF_HUB_OFFLINE
```

Exit codes: 0 OK, 1 error, 2 mutation detected, 3 the Chroma copy in
`frozen\_chroma_copy` could not be deleted. It holds real data: delete it by hand.

## 5. Hashes of the frozen retrieval

```powershell
Get-Content private\scratch\extractive_spike\frozen\HASHES.txt
Get-FileHash -Algorithm SHA256 private\scratch\extractive_spike\frozen\HASHES.txt
```

`run.py` checks every `frozen_*.json` against `HASHES.txt` and refuses to run on a mismatch.

## 6. Isolated runs: E1, then E2, then V4

Replace `<MODEL>` with the value of `OLLAMA_GEN_MODEL` in `backend\.env`.
Each variant runs in its own process. Before every question the model is
unloaded, `/api/ps` is checked and a warm-up call is made.

```powershell
.\backend\.venv\Scripts\python.exe evals\spikes\extractive\run.py --variant E1 --mode isolated --model <MODEL> --frozen-dir private\scratch\extractive_spike\frozen --out private\scratch\extractive_spike\out
.\backend\.venv\Scripts\python.exe evals\spikes\extractive\run.py --variant E2 --mode isolated --model <MODEL> --frozen-dir private\scratch\extractive_spike\frozen --out private\scratch\extractive_spike\out
.\backend\.venv\Scripts\python.exe evals\spikes\extractive\run.py --variant V4 --mode isolated --model <MODEL> --frozen-dir private\scratch\extractive_spike\frozen --out private\scratch\extractive_spike\out
```

E1 and E2 start with a format self-test: one call with a trivial JSON schema.
If it fails, the run stops before any question with exit code 4.

Exit codes: 0 OK, 1 error, 4 format self-test failed.

## 7. Sequential run, only for a variant that passed

Judge the isolated runs against `PREREG.md` first. Then, for each extractive
variant that passed (example for E2):

```powershell
.\backend\.venv\Scripts\python.exe evals\spikes\extractive\run.py --variant E2 --mode sequential --model <MODEL> --frozen-dir private\scratch\extractive_spike\frozen --out private\scratch\extractive_spike\out
```

## Output

`private\scratch\extractive_spike\out\<mode>\<variant>\`:

- `<label>.json` per question (`C4`, `T15`, `C1a`, `T17`, `B09`, `T18`, `C1b`):
  raw content, parse status, every quote with its verification result and reason,
  `quote_text`, displays with period, final decision, Ollama counts and durations,
  time, flags (`CTX_NEAR_LIMIT`, `OUTPUT_TRUNCATED`), top rerank score.
  Isolated runs also keep `ps_before` and the warm-up record.
- `run_meta.json`: Ollama version, parameters, self-test result, frozen hashes,
  and whether C1a and C1b are identical byte for byte.

A run refuses to write into a non-empty output folder.
