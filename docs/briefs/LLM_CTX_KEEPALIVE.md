# LLM_CTX_KEEPALIVE

## CONTEXT
`backend/app/retrieval/llm.py` (OllamaClient) περνάει στο `/api/chat` μόνο
`temperature` και `seed` στο `options`. Δεν περνάει `num_ctx` ούτε `keep_alive`.

Συνέπειες:
- `num_ctx`: το Ollama χρησιμοποιεί το default του μοντέλου (131072 για Krikri),
  που δίνει ~23.2 GB KV cache σε μηχάνημα 16 GB και προκαλεί swap.
- `keep_alive`: default 5 λεπτά, οπότε το μοντέλο ξεφορτώνεται μεταξύ ερωτήσεων
  και η επόμενη πληρώνει ξανά το cold load. Σε παρουσίαση αυτό είναι ορατό.

ΖΗΤΟΥΜΕΝΟ: να γίνουν και τα δύο ρυθμίσεις, με το ΙΔΙΟ pattern που ήδη
ακολουθούν temperature/seed (default στο config.py, override στον constructor).

Το μηχάνημα είναι Mac και το Krikri ΔΕΝ τρέχει εδώ. Δεν γίνεται live έλεγχος
σε αυτή τη session. Ο κώδικας γράφεται εδώ, το live test θα γίνει σε Windows.

## ΦΑΣΗ 0 - RECON (ΥΠΟΧΡΕΩΤΙΚΗ, HARD STOP ΣΤΟ ΤΕΛΟΣ)
Καμία αλλαγή αρχείου.

1. `git status` και `git log --oneline -1` (περιμένω `61b3ee2` στο main), RAW.
2. `cat backend/app/retrieval/llm.py` RAW.
3. `cat backend/app/core/config.py` RAW. Θέλω να δω ΟΛΟ το Settings, όχι grep.
4. `grep -rn "OllamaClient(" backend/ --include=*.py | grep -v "\.venv"` RAW.
   Κάθε σημείο που κατασκευάζει client, ώστε να ξέρω τι σπάει αν αλλάξει η
   υπογραφή.
5. `grep -rn "OllamaClient\|FakeLLM" backend/tests/*.py` RAW. Ποια tests
   αγγίζουν αυτό το path.
6. Πες μου: υπάρχει ήδη test που ελέγχει το payload που στέλνεται στο Ollama
   (δηλαδή που κάνει mock το `requests.post` και επιθεωρεί το json); Αν ναι,
   ποιο και πού.

ΣΤΑΜΑΤΑ ΕΔΩ. Περίμενε έγκριση.

## ΦΑΣΗ 1 - IMPLEMENTATION (μόνο μετά από έγκριση)

### config.py
Δύο νέες ρυθμίσεις δίπλα στις υπάρχουσες OLLAMA_*:
- `OLLAMA_NUM_CTX: int = 8192`
- `OLLAMA_KEEP_ALIVE: str = "30m"`

Το 8192 είναι συντηρητική τιμή που χωράει άνετα σε 16 GB. Δεν το βελτιστοποιούμε
εδώ, θα μετρηθεί σε Windows. ΜΗΝ διαλέξεις άλλη τιμή χωρίς να ρωτήσεις.

### llm.py
- Δύο νέες παράμετροι στον constructor, `num_ctx: int | None = None` και
  `keep_alive: str | None = None`, με το ίδιο `if not None else settings.X`
  pattern που ήδη υπάρχει. ΤΟ ΙΔΙΟ, όχι δικό σου.
- `num_ctx` μπαίνει ΜΕΣΑ στο `options`, δίπλα σε temperature/seed.
- `keep_alive` μπαίνει στο TOP LEVEL του json, ΟΧΙ μέσα στο options.
  Αυτό είναι το Ollama API contract, μην το βάλεις λάθος.

### tests
Νέο ή επαυξημένο test που κάνει mock το `requests.post` και επιθεωρεί το
payload. Θέλω ΚΑΙ ΤΑ ΔΥΟ:
- POSITIVE: το payload περιέχει `options.num_ctx` == η ρύθμιση, και
  `keep_alive` στο top level == η ρύθμιση.
- NEGATIVE: το `keep_alive` ΔΕΝ βρίσκεται μέσα στο `options`. Αν κάποιος το
  μετακινήσει εκεί, το Ollama το αγνοεί σιωπηλά και το test πρέπει να πέσει.
Αν στη ΦΑΣΗ 0 βρήκες υπάρχον test payload inspection, επαύξησέ το αντί να
φτιάξεις δεύτερο.

## ΤΙ ΝΑ ΜΗΝ ΑΓΓΙΞΕΙΣ
- `semantic.py`, `structured.py`, `routing.py`, `reranker.py`
- Οποιοδήποτε prompt file
- Το `.env` (δεν υπάρχει στο git, δεν το πειράζουμε)
- Τη βάση
- Τη σειρά ή τις τιμές των υπαρχουσών ρυθμίσεων

## ΦΑΣΗ 2 - VERIFY
1. Το test file του llm, RAW output.
2. Full backend sweep, ένα αρχείο τη φορά με `PYTHONPATH=. python`, ΟΧΙ pytest.
   Μετρημένος αριθμός αρχείων, όχι εκτίμηση.
3. MUTATION CHECK: `git status --porcelain` (αναμένω llm.py, config.py, το test
   file, και το γνωστό `?? start.sh`), `git diff --stat`, DB αμετάβλητη
   (persons=1, evaluations=36, field_scores=37, documents=37, promotions=3,
   service_time=9).
4. RAW. Μην συνοψίζεις αριθμούς που δεν μέτρησες.

## STOP CONDITIONS
- ΟΧΙ commit, push, branch, `git add`.
- Αν κάποιο test εκτός των δικών σου πέσει, ΣΤΑΜΑΤΑ.
- Αν χρειαστεί αλλαγή εκτός των τριών αρχείων, ΣΤΑΜΑΤΑ και ρώτα.
- ΜΗΝ προσπαθήσεις να τρέξεις live κλήση στο Ollama. Δεν τρέχει εδώ.
