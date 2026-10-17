import type { ReactNode } from 'react'
import type { OverallFieldScore, PersonOut, SemanticResult, StructuredResult } from '../api/types'
import { SemanticAnswer } from './SemanticAnswer'
import { EmptyState } from './EmptyState'
import { CitationList } from './CitationBadge'
import { PersonHeading } from './PersonHeading'

interface Section {
  section: string
  score: number
  comment: string
}

interface FieldScore {
  field_code: string
  description: string
  value: number | string
}

interface Evaluator {
  rank?: string
  name?: string
  role?: string
}

interface EvaluationEntry {
  person_id?: string
  period?: string
  ea_type?: string
  characterization?: string
  score?: number
  unit?: string
  evaluator?: Evaluator
  field_scores?: FieldScore[]
}

// Οριζόντιο scroll ΜΕΣΑ στον πίνακα σε στενό παράθυρο, όχι σε όλη τη σελίδα.
function ScrollTable({ children }: { children: ReactNode }) {
  return (
    <div data-testid="table-scroll" className="max-w-full overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  )
}

interface TopBottomItem {
  label: string
  value: number
}

function isSection(value: unknown): value is Section {
  return (
    typeof value === 'object' &&
    value !== null &&
    'section' in value &&
    'score' in value
  )
}

function toTopBottomItem(item: Record<string, unknown>): TopBottomItem {
  return {
    label: String(item.description ?? item.field_code ?? ''),
    value: Number(item.value ?? 0),
  }
}

function SectionsTable({ sections, title }: { sections: Section[]; title?: string }) {
  return (
    <div className="flex flex-col gap-1">
      {title && (
        <h3 className="text-sm font-semibold" style={{ color: '#e6eaf2' }}>
          {title}
        </h3>
      )}
      <ScrollTable>
        <thead>
          <tr className="border-b text-left" style={{ borderColor: '#2a3756' }}>
            <th className="py-1">Ενότητα</th>
            <th className="py-1">Βαθμολογία</th>
            <th className="py-1">Σχόλιο</th>
          </tr>
        </thead>
        <tbody>
          {sections.map((s, idx) => (
            <tr key={`${s.section}-${idx}`} className="border-b" style={{ borderColor: '#1e2a44' }}>
              <td className="py-1">{s.section}</td>
              <td className="py-1 font-mono">{s.score}</td>
              <td className="py-1">{s.comment}</td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </div>
  )
}

function TopBottomTable({ items, title }: { items: TopBottomItem[]; title: string }) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-sm font-semibold" style={{ color: '#e6eaf2' }}>
        {title}
      </h3>
      <ScrollTable>
        <thead>
          <tr className="border-b text-left" style={{ borderColor: '#2a3756' }}>
            <th className="py-1 pr-2">Ενότητα</th>
            <th className="py-1 w-24">Βαθμολογία</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it, idx) => (
            <tr key={`${it.label}-${idx}`} className="border-b" style={{ borderColor: '#1e2a44' }}>
              <td className="py-1 pr-2">{it.label}</td>
              <td className="py-1 font-mono">{it.value}</td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </div>
  )
}

function toOverallFieldScore(item: Record<string, unknown>): OverallFieldScore {
  return {
    field_code: String(item.field_code ?? ''),
    description: String(item.description ?? ''),
    value: Number(item.value ?? 0),
  }
}

// Ξεχωριστά από τα top/bottom: είναι η συνολική ολιστική κρίση του αξιολογητή,
// όχι πεδίο επίδοσης, οπότε δεν συγκρίνεται με τα υπόλοιπα.
function OverallField({ overall }: { overall: OverallFieldScore }) {
  return (
    <div
      className="flex flex-col gap-1 rounded border p-3"
      style={{ borderColor: '#2a3756' }}
    >
      <h3 className="text-sm font-semibold" style={{ color: '#e6eaf2' }}>
        Συνολική κρίση (εκτός κατάταξης)
      </h3>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span>{overall.description || overall.field_code}</span>
        <span className="font-mono">{overall.value}</span>
      </div>
      <p className="text-xs" style={{ color: '#a9b4c8' }}>
        Ολιστική κρίση του αξιολογητή - δεν είναι συγκρίσιμη με τα επιμέρους πεδία.
      </p>
    </div>
  )
}

function FieldScoresTable({ scores }: { scores: FieldScore[] }) {
  return (
    <ScrollTable>
      <thead>
        <tr className="border-b text-left" style={{ borderColor: '#2a3756' }}>
          <th className="py-1 pr-2 w-16">Κωδικός</th>
          <th className="py-1 pr-2">Περιγραφή</th>
          <th className="py-1 w-20">Τιμή</th>
        </tr>
      </thead>
      <tbody>
        {scores.map((s, idx) => (
          <tr key={`${s.field_code}-${idx}`} className="border-b" style={{ borderColor: '#1e2a44' }}>
            <td className="py-1 pr-2 font-mono">{s.field_code}</td>
            <td className="py-1 pr-2">{s.description}</td>
            <td className="py-1 font-mono">{String(s.value)}</td>
          </tr>
        ))}
      </tbody>
    </ScrollTable>
  )
}

function EntryDetails({ entry, title }: { entry: EvaluationEntry; title?: string }) {
  const evaluator = entry.evaluator
  return (
    <div className="flex flex-col gap-3">
      {title && (
        <h3 className="text-sm font-semibold" style={{ color: '#e6eaf2' }}>
          {title}
        </h3>
      )}

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm" style={{ color: '#c4ccdb' }}>
        {entry.ea_type && (
          <>
            <span style={{ color: '#a9b4c8' }}>Τύπος έκθεσης</span>
            <span>{entry.ea_type}</span>
          </>
        )}
        {entry.characterization && (
          <>
            <span style={{ color: '#a9b4c8' }}>Χαρακτηρισμός</span>
            <span>{entry.characterization}</span>
          </>
        )}
        {entry.score !== undefined && entry.score !== null && (
          <>
            <span style={{ color: '#a9b4c8' }}>Συνολική βαθμολογία</span>
            <span className="font-mono">{entry.score}</span>
          </>
        )}
        {entry.unit && (
          <>
            <span style={{ color: '#a9b4c8' }}>Μονάδα</span>
            <span>{entry.unit}</span>
          </>
        )}
        {evaluator && (evaluator.rank || evaluator.name || evaluator.role) && (
          <>
            <span style={{ color: '#a9b4c8' }}>Αξιολογητής</span>
            <span>
              {[evaluator.rank, evaluator.name, evaluator.role].filter(Boolean).join(' - ')}
            </span>
          </>
        )}
      </div>

      {Array.isArray(entry.field_scores) && entry.field_scores.length > 0 && (
        <div className="flex flex-col gap-1">
          <h4 className="text-xs font-semibold uppercase" style={{ color: '#a9b4c8' }}>
            Αναλυτικές βαθμολογίες
          </h4>
          <FieldScoresTable scores={entry.field_scores} />
        </div>
      )}
    </div>
  )
}

// Τιμές πινάκων VERBATIM όπως στη DB: η πηγή έχει σκόπιμα αλλοιωμένες τιμές
// (π.χ. "02//02/04/2013"), καμία διόρθωση ή μορφοποίηση ημερομηνιών εδώ.
// Μόνο το null/απόν εμφανίζεται ως "-".
function verbatim(value: unknown): string {
  return value === null || value === undefined ? '-' : String(value)
}

interface TableColumn {
  key: string
  label: string
  mono?: boolean
}

const PROMOTION_COLUMNS: TableColumn[] = [
  { key: 'rank', label: 'Βαθμός' },
  { key: 'promotion_date', label: 'Ημ. προαγωγής', mono: true },
  { key: 'decision_date', label: 'Ημ. απόφασης', mono: true },
  { key: 'decision', label: 'Απόφαση' },
  { key: 'judged_for', label: 'Κρίθηκε για' },
]

const SERVICE_TIME_COLUMNS: TableColumn[] = [
  { key: 'subsection', label: 'Υποενότητα' },
  { key: 'label', label: 'Περιγραφή' },
  { key: 'years', label: 'Έτη', mono: true },
  { key: 'months', label: 'Μήνες', mono: true },
  { key: 'days', label: 'Ημέρες', mono: true },
]

function RowsTable({
  rows,
  columns,
  title,
}: {
  rows: Record<string, unknown>[]
  columns: TableColumn[]
  title: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-sm font-semibold" style={{ color: '#e6eaf2' }}>
        {title}
      </h3>
      <ScrollTable>
        <thead>
          <tr className="border-b text-left" style={{ borderColor: '#2a3756' }}>
            {columns.map((col) => (
              <th key={col.key} className="py-1 pr-2">
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={`${verbatim(row.row_index)}-${idx}`} className="border-b" style={{ borderColor: '#1e2a44' }}>
              {columns.map((col) => (
                <td key={col.key} className={col.mono ? 'py-1 pr-2 font-mono' : 'py-1 pr-2'}>
                  {verbatim(row[col.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </div>
  )
}

// get_promotions_table / get_service_time_table: `data.rows`, ξεχωρίζουν από
// τα πεδία της πρώτης γραμμής (rank -> προαγωγές, subsection -> χρόνος υπηρεσίας).
function CareerRows({ rows }: { rows: Record<string, unknown>[] }) {
  if (rows.length === 0) {
    return <EmptyState message="Δεν βρέθηκαν εγγραφές" />
  }
  if ('subsection' in rows[0]) {
    return <RowsTable rows={rows} columns={SERVICE_TIME_COLUMNS} title="Συνολικός χρόνος υπηρεσίας" />
  }
  return <RowsTable rows={rows} columns={PROMOTION_COLUMNS} title="Κρίσεις προαγωγών" />
}

function isEvaluationEntry(data: Record<string, unknown>): boolean {
  return (
    'field_scores' in data ||
    'characterization' in data ||
    'ea_type' in data ||
    'evaluator' in data
  )
}

function StructuredView({ result, auditId }: { result: StructuredResult; auditId: number }) {
  const data = result.data
  const hasData = Object.keys(data).length > 0

  return (
    <div className="flex flex-col gap-4">
      {!hasData && <EmptyState message="Δεν βρέθηκαν βαθμολογίες στο εύρος" />}

      {Array.isArray(data.sections) && data.sections.every(isSection) && (
        <SectionsTable sections={data.sections} />
      )}

      {!!data.entry_a && !!data.entry_b && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <EntryDetails
            entry={data.entry_a as EvaluationEntry}
            title={String(data.period_a ?? 'Περίοδος Α')}
          />
          <EntryDetails
            entry={data.entry_b as EvaluationEntry}
            title={String(data.period_b ?? 'Περίοδος Β')}
          />
        </div>
      )}

      {Array.isArray(data.sections_a) && Array.isArray(data.sections_b) && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <SectionsTable sections={data.sections_a as Section[]} title={String(data.period_a ?? 'Περίοδος Α')} />
          <SectionsTable sections={data.sections_b as Section[]} title={String(data.period_b ?? 'Περίοδος Β')} />
        </div>
      )}

      {data.overall != null && typeof data.overall === 'object' && (
        <OverallField overall={toOverallFieldScore(data.overall as Record<string, unknown>)} />
      )}

      {Array.isArray(data.top) && Array.isArray(data.bottom) && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <TopBottomTable
            items={(data.top as Record<string, unknown>[]).map(toTopBottomItem)}
            title="Κορυφαίες ενότητες"
          />
          <TopBottomTable
            items={(data.bottom as Record<string, unknown>[]).map(toTopBottomItem)}
            title="Χαμηλότερες ενότητες"
          />
        </div>
      )}

      {!Array.isArray(data.sections) &&
        !data.entry_a &&
        !Array.isArray(data.sections_a) &&
        !Array.isArray(data.top) &&
        isEvaluationEntry(data) && (
          <EntryDetails entry={data as EvaluationEntry} />
        )}

      {Array.isArray(data.rows) && <CareerRows rows={data.rows as Record<string, unknown>[]} />}

      <CitationList citations={result.citations} />

      <p className="font-mono text-xs" style={{ color: '#a9b4c8' }}>
        Καταχώρηση ελέγχου: #{auditId}
      </p>
    </div>
  )
}

interface ResultsPanelProps {
  result: StructuredResult | SemanticResult | null
  auditId: number | null
  // Υποχρεωτικό: κανένα αποτέλεσμα δεν εμφανίζεται χωρίς ρητό «σε ποιον αφορά».
  person: PersonOut
}

export function ResultsPanel({ result, auditId, person }: ResultsPanelProps) {
  if (!result || auditId === null) {
    return <EmptyState message="Υποβάλετε ένα ερώτημα για να δείτε αποτελέσματα" />
  }

  return (
    <div
      className="flex flex-col gap-3 rounded-2xl border p-5"
      style={{ borderColor: '#2a3756', backgroundColor: '#0f1a2f' }}
    >
      <PersonHeading person={person} testId="results-person" />
      {result.mode === 'semantic' ? (
        <SemanticAnswer
          answer={result.answer}
          citations={result.citations}
          auditId={auditId}
          routingHint={result.routing_hint}
          refusalReason={result.refusal_reason}
        />
      ) : (
        <StructuredView result={result} auditId={auditId} />
      )}
    </div>
  )
}