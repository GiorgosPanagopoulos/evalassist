# EvalAssist: εγκατάσταση structured-only

Οδηγίες για τον διαχειριστή του server. Το πρώτο deploy είναι **χωρίς
σημασιολογική αναζήτηση** (`SEMANTIC_ENABLED=false`): λειτουργούν login,
διαχείριση χρηστών, δομημένες ερωτήσεις και timeline. Δεν χρειάζονται GPU,
μοντέλα, torch, ChromaDB ή Ollama.

Κάθε `<CHANGEME_...>` είναι τιμή του server που συμπληρώνει ο διαχειριστής.
Τα βήματα γίνονται με τη σειρά. Οι εντολές είναι για Linux.

## Τι εγκαθίσταται και τι όχι

- Η εφαρμογή χρησιμοποιεί την Python που υπάρχει ήδη στον server, μέσα σε
  ένα virtualenv στον φάκελο της εφαρμογής. Δεν γίνεται εγκατάσταση πακέτων
  στο σύστημα.
- Python πακέτα: μόνο τα 18 του `backend/requirements-deploy.txt`. Είναι 6
  άμεσες εξαρτήσεις (FastAPI, uvicorn, pydantic, pydantic-settings,
  python-dotenv, httpx) και 12 έμμεσες. Όλα έχουν ακριβή έκδοση, ώστε ο server
  να εγκαθιστά ακριβώς ό,τι δοκιμάστηκε.
- Node.js χρειάζεται **μόνο για το build** του frontend (βήμα 3). Μπορεί να
  γίνει και σε άλλο μηχάνημα, και να μεταφερθεί μόνο ο φάκελος
  `frontend/dist/`. Στο runtime δεν χρειάζεται Node.
- Το `pip install` και το `npm ci` χρειάζονται internet, άρα γίνονται μέσα
  στο ωράριο που έχει internet ο server. Στο runtime η εφαρμογή δεν κάνει
  καμία εξωτερική κλήση. Το `npm run check:dist` (βήμα 3) ελέγχει ότι και το
  frontend δεν ζητά τίποτα εκτός του δικού του origin.

## 1. Προαπαιτούμενα

| | Έκδοση |
|---|---|
| Python | ≥ 3.11 (στον server: `<CHANGEME_PYTHON>`), με `venv`, `sqlite3` και `hashlib.scrypt` |
| Node.js + npm | μόνο για το build, δοκιμασμένο με Node 24 (`<CHANGEME_NODE>`) |

Έλεγχος της Python:

```sh
python3 --version
python3 -c "import sqlite3, hashlib, venv; hashlib.scrypt(b'x', salt=b'y', n=2, r=1, p=1); print('ok', sqlite3.sqlite_version)"
```

Το `hashlib.scrypt` απαιτεί Python χτισμένη με OpenSSL 1.1 ή νεότερο. Αν η
δεύτερη εντολή αποτύχει, η εφαρμογή δεν μπορεί να ελέγξει κωδικούς.

## 2. Κώδικας και Python πακέτα

Ο φάκελος της εφαρμογής κρατά τη δομή του repo: το backend βρίσκει το build
του frontend στο `../frontend/dist` σε σχέση με το `backend/`.

```sh
cd <CHANGEME_APP_DIR>
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-deploy.txt
```

Αν ο server δεν έχει πρόσβαση στο PyPI, τα wheels κατεβαίνουν σε άλλο
μηχάνημα με την ίδια έκδοση Python και πλατφόρμα (`pip download -r
backend/requirements-deploy.txt -d wheels`) και εγκαθίστανται με
`.venv/bin/pip install --no-index --find-links wheels -r backend/requirements-deploy.txt`.

## 3. Build του frontend

**Χωρίς `NODE_ENV` στο shell.** Με `NODE_ENV=production` το `npm ci` παραλείπει
τα devDependencies (TypeScript, Vite) και το build αποτυγχάνει. Το `env -u`
το αφαιρεί μόνο για την εντολή:

```sh
cd <CHANGEME_APP_DIR>/frontend
env -u NODE_ENV npm ci
env -u NODE_ENV npm run build
npm run check:dist
```

Το `check:dist` πρέπει να τελειώσει χωρίς ευρήματα. Αν βρει εξωτερική
διεύθυνση στο build, **δεν** συνεχίζουμε.

## 4. Ρυθμίσεις

```sh
cp <CHANGEME_APP_DIR>/deploy/.env.production.example <CHANGEME_APP_DIR>/backend/.env
chmod 600 <CHANGEME_APP_DIR>/backend/.env
```

**Το `backend/.env` αποθηκεύεται σε UTF-8 χωρίς BOM**, και η πρώτη γραμμή του
μένει σχόλιο. Με BOM (το προσθέτουν ορισμένοι editors, κυρίως στα Windows) η
πρώτη ρύθμιση του αρχείου αγνοείται σιωπηλά και παίρνει την default τιμή της.
Από αυτή την έκδοση το app διαβάζει σωστά και αρχείο με BOM, αλλά η σύσταση
μένει για παλαιότερες εκδόσεις και για άλλα εργαλεία που διαβάζουν το αρχείο.
Έλεγχος, όπου το αποτέλεσμα πρέπει να είναι `0`:

```sh
head -c 3 <CHANGEME_APP_DIR>/backend/.env | grep -c $'\xef\xbb\xbf'
```

Συμπληρώνονται τα `<CHANGEME_...>` του αρχείου. Κάθε γραμμή έχει σχόλιο. Το
app διαβάζει μόνο το `backend/.env` και μεταβλητές περιβάλλοντος της
διεργασίας (που υπερισχύουν). Τα σημαντικά:

- `SEMANTIC_ENABLED=false`, `ACCESS_LOG=false`, `ENABLE_DOCS=false`: μένουν ως έχουν.
- `DB_PATH`: absolute path της βάσης του βήματος 5.
- `COOKIE_SECURE=true`: το session cookie στέλνεται μόνο σε HTTPS.
- `COOKIE_PATH`: εξαρτάται από το portal, βλ. την αντίστοιχη ενότητα.

**Όταν ανοίξει το semantic (όχι σε αυτό το deploy):** το `HF_HUB_OFFLINE=1`
πρέπει να οριστεί ως **μεταβλητή περιβάλλοντος της διεργασίας** (π.χ. στο
service), ώστε να μη γίνεται καμία κλήση στο HuggingFace Hub. Από το
`backend/.env` **δεν διαβάζεται**: το αρχείο τροφοδοτεί μόνο τις ρυθμίσεις του
app, ενώ το `HF_HUB_OFFLINE` το βλέπει η βιβλιοθήκη huggingface_hub μόνο στο
περιβάλλον της διεργασίας. Με το semantic κλειστό η βιβλιοθήκη δεν φορτώνεται
και η ρύθμιση δεν χρειάζεται.

## 5. Βάση δεδομένων

Η βάση **δεν** είναι αντίγραφο της βάσης ανάπτυξης. Χτίζεται με το
`deploy/build_deploy_db.py` από την ομάδα ανάπτυξης και παραδίδεται έτοιμη:

- έχει μόνο τους πίνακες δεδομένων (persons, evaluations, field_scores,
  documents, promotions, service_time),
- δεν έχει χρήστες, sessions, auth_log ή audit_log της μηχανής ανάπτυξης,
- έχει ήδη το τρέχον schema.

Περιέχει προσωπικά δεδομένα: μεταφέρεται μόνο με το κανάλι που έχει
συμφωνηθεί, και στον server:

```sh
install -m 600 <παραδοθέν αρχείο> <CHANGEME_DB_PATH>
```

Ο ιδιοκτήτης του αρχείου και του φακέλου του είναι ο χρήστης της υπηρεσίας:
το SQLite γράφει δίπλα στη βάση προσωρινά αρχεία (journal).

## 6. Migration, ΠΡΙΝ από το API

Το API **δεν** τρέχει migrations στο startup. Πριν από την πρώτη εκκίνηση,
και μετά από κάθε αναβάθμιση του κώδικα:

```sh
cp <CHANGEME_DB_PATH> <CHANGEME_BACKUP_DIR>/evalassist-$(date +%Y%m%d-%H%M).db   # backup
cd <CHANGEME_APP_DIR>/backend
../.venv/bin/python -m app.db.database
```

Τρέχει όσες φορές χρειαστεί χωρίς να αλλάξει κάτι αν η βάση είναι ήδη
ενημερωμένη.

## 7. Πρώτος admin

```sh
cd <CHANGEME_APP_DIR>/backend
../.venv/bin/python -m app.auth.create_admin
```

Ζητά username και κωδικό δύο φορές (τουλάχιστον 12 χαρακτήρες). Ο κωδικός
διαβάζεται χωρίς να εμφανίζεται, δεν δίνεται ποτέ ως όρισμα και δεν γράφεται
σε αρχείο ή log. Τους υπόλοιπους χρήστες τους δημιουργεί ο admin από το UI
(«Χρήστες»), με προσωρινό κωδικό που αλλάζει στην πρώτη σύνδεση.

## 8. Εκκίνηση

```sh
cd <CHANGEME_APP_DIR>/backend
../.venv/bin/uvicorn app.api.main:app --host 127.0.0.1 --port <CHANGEME_PORT>
```

- **Χωρίς `--reload`** (μόνο για ανάπτυξη).
- Μόνο σε `127.0.0.1`: πρόσβαση από έξω μόνο μέσω του portal.
- Ένας worker (default): η βάση είναι SQLite.
- Working directory το `backend/`.

Πώς τρέχει ως υπηρεσία (π.χ. systemd) το αποφασίζει ο διαχειριστής. Αρκεί να
κρατά τα παραπάνω και να τρέχει με χρήστη που έχει δικαίωμα εγγραφής στη βάση.

## 9. Έλεγχος μετά την εγκατάσταση

1. **Health**

   ```sh
   curl -s http://127.0.0.1:<CHANGEME_PORT>/api/health
   ```

   Αναμένεται `{"status":"ok","ollama_reachable":null}`. Το `null` σημαίνει
   «δεν ελέγχθηκε»: με το semantic κλειστό ο server δεν καλεί καθόλου το
   Ollama. Το UI δείχνει πράσινο «Σύστημα ενεργό». Αν το API δεν απαντά, το UI
   δείχνει πορτοκαλί «Σύστημα μη διαθέσιμο».

2. **Login, δομημένη ερώτηση, semantic → 403, logout**

   ```sh
   cd <CHANGEME_APP_DIR>
   .venv/bin/python deploy/smoke_test.py http://127.0.0.1:<CHANGEME_PORT>
   ```

   Ζητά username και κωδικό (του admin του βήματος 7), ένα person_id και μία
   περίοδο (`YYYY-MM-DD..YYYY-MM-DD`) για τη δομημένη ερώτηση. Πρέπει να δώσει
   7 γραμμές `OK` και να τελειώσει με «Όλοι οι έλεγχοι πέρασαν.» Δεν τυπώνει
   κωδικό, cookie ή δεδομένα. Οι κλήσεις του γράφονται κανονικά στο audit_log.

   Γιατί script και όχι curl: το session cookie είναι `Secure` και σε
   `http://127.0.0.1` το curl δεν το ξαναστέλνει. Το script το στέλνει ρητά.

3. **API docs κλειστά**

   ```sh
   curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:<CHANGEME_PORT>/docs
   ```

   Αναμένεται `404`.

4. **Logs χωρίς περιεχόμενο.** Στα logs της υπηρεσίας μετά το βήμα 2 δεν
   πρέπει να υπάρχει ούτε το person_id που δόθηκε ούτε URL του API. Για
   παράδειγμα, με systemd:

   ```sh
   journalctl -u <CHANGEME_SERVICE> --since "-15 min" | grep -c "<το person_id του βήματος 2>"
   journalctl -u <CHANGEME_SERVICE> --since "-15 min" | grep -c "/api/"
   ```

   Και τα δύο πρέπει να δώσουν `0`. Το access log είναι κλειστό από τον κώδικα
   (`ACCESS_LOG=false`) και οι εξαιρέσεις γράφουν μόνο τύπο και αρχείο:γραμμή.

## Portal / reverse proxy

*Συμπληρώνεται όταν οριστεί το portal.* Ό,τι χρειάζεται να καλύψει:

- HTTPS προς τον browser. Το cookie είναι `Secure` και χωρίς HTTPS το login
  δεν κρατά session.
- Προώθηση του `https://<CHANGEME_PORTAL_HOST>/<CHANGEME_PREFIX>/` στο
  `http://127.0.0.1:<CHANGEME_PORT>/`, **με αφαίρεση του prefix**. Το frontend
  χρησιμοποιεί σχετικά paths και δουλεύει κάτω από οποιοδήποτε prefix.
- `COOKIE_PATH` στο `backend/.env`: `/<CHANGEME_PREFIX>` αν η εφαρμογή είναι
  κάτω από prefix, `/` αν είναι στη ρίζα του host.
- Frontend και API στο ίδιο origin. Το app δεν έχει CORS και δεν το
  χρειάζεται.
- Χωρίς cache στο `/<CHANGEME_PREFIX>/api/`.
