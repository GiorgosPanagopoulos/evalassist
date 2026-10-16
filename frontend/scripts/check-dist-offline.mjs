// Έλεγχος μετά το `vite build`: το dist δεν πρέπει να περιέχει καμία εξωτερική
// διεύθυνση. Η εφαρμογή τρέχει σε μηχάνημα με internet μόνο 07:00-17:00, άρα
// στο runtime δεν επιτρέπεται κανένα request εκτός του δικού της origin
// (fonts, CDNs, analytics κ.λπ.).
//
// Χρήση: node scripts/check-dist-offline.mjs [dist-dir]
// Exit 1 με λίστα ευρημάτων αν βρεθεί κάτι. Καμία εξάρτηση.
//
// Εξαιρέσεις, και ΜΟΝΟ αυτές:
// - Σχόλια license (/*! ... */ και block comments με @license ή @preserve)
//   αφαιρούνται πριν από τον έλεγχο: είναι κείμενο, όχι κώδικας.
// - Τα 4 XML namespaces παρακάτω, με ακριβή σύγκριση ολόκληρου του URL. Το
//   React (και τα SVG του public/) τα χρησιμοποιεί ως αναγνωριστικά σε
//   createElementNS/setAttributeNS και στο xmlns. Ο browser δεν τα ζητά ποτέ.
// - Το https://react.dev/errors/ ως prefix: το production React χτίζει από
//   αυτό το κείμενο των μηνυμάτων σφάλματος (ακολουθεί ο κωδικός σφάλματος).
//   Δεν γίνεται request, μόνο εμφανίζεται σε ένα μήνυμα.

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { extname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ALLOWED_EXACT = new Set([
  'http://www.w3.org/2000/svg',
  'http://www.w3.org/1999/xlink',
  'http://www.w3.org/1998/Math/MathML',
  'http://www.w3.org/XML/1998/namespace',
])
const ALLOWED_PREFIX = ['https://react.dev/errors/']

const FORBIDDEN_WORDS = ['googleapis', 'gstatic']

const TEXT_EXTENSIONS = new Set(['.html', '.js', '.mjs', '.css', '.svg', '.json', '.txt', '.map', '.webmanifest', '.xml'])

// Ό,τι μοιάζει με URL μέχρι τον πρώτο χαρακτήρα που δεν ανήκει σε URL.
const URL_RE = /(?:https?:)?\/\/[a-z0-9.-]+\.[a-z]{2,}[^\s"'`()<>\\]*/gi
const LICENSE_COMMENT_RE = /\/\*(?:!|[\s\S]*?@(?:license|preserve))[\s\S]*?\*\//g

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) yield* walk(path)
    else yield path
  }
}

function isAllowed(url) {
  return ALLOWED_EXACT.has(url) || ALLOWED_PREFIX.some((prefix) => url.startsWith(prefix))
}

export function findExternalReferences(text) {
  const stripped = text.replace(LICENSE_COMMENT_RE, '')
  const findings = []
  for (const match of stripped.matchAll(URL_RE)) {
    let url = match[0]
    // Το React γράφει π.χ. `https://react.dev/errors/`+e: το backtick κόβει
    // ήδη το URL. Τελικά σημεία στίξης δεν ανήκουν στο URL.
    url = url.replace(/[.,;:]+$/, '')
    if (url.startsWith('//')) {
      findings.push(url)
      continue
    }
    if (!isAllowed(url)) findings.push(url)
  }
  const lower = stripped.toLowerCase()
  for (const word of FORBIDDEN_WORDS) {
    if (lower.includes(word)) findings.push(word)
  }
  return findings
}

export function checkDist(distDir) {
  const problems = []
  for (const path of walk(distDir)) {
    if (!TEXT_EXTENSIONS.has(extname(path).toLowerCase())) continue
    const findings = findExternalReferences(readFileSync(path, 'utf8'))
    for (const finding of new Set(findings)) problems.push(`${relative(distDir, path)}: ${finding}`)
  }
  return problems
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const distDir = resolve(process.argv[2] ?? 'dist')
  const problems = checkDist(distDir)
  if (problems.length > 0) {
    console.error(`Εξωτερικές διευθύνσεις στο ${distDir}:`)
    for (const problem of problems) console.error(`  ${problem}`)
    process.exit(1)
  }
  console.log(`OK: καμία εξωτερική διεύθυνση στο ${distDir}`)
}
