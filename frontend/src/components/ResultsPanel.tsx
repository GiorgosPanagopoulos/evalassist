import type { SemanticResult, StructuredResult } from '../api/types'
import { SemanticAnswer } from './SemanticAnswer'
import { EmptyState } from './EmptyState'

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
        <h3 className="text-sm font-semibold" style={{ color: '#f2f2f4' }}>
          {title}
        </h3>
      )}
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b text-left" style={{ borderColor: '#26262d' }}>
            <th className="py-1">Ενότητα</th>
            <th className="py-1">Βαθμολογία</th>
            <th className="py-1">Σχόλιο</th>
          </tr>
        </thead>
        <tbody>
          {sections.map((s, idx) => (
            <tr key={`${s.section}-${idx}`} className="border-b" style={{ borderColor: '#1d1d22' }}>
              <td className="py-1">{s.section}</td>
              <td className="py-1 font-mono">{s.score}</td>
              <td className="py-1">{s.comment}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TopBottomTable({ items, title }: { items: TopBottomItem[]; title: string }) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-sm font-semibold" style={{ color: '#f2f2f4' }}>
        {title}
      </h3>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b text-left" style={{ borderColor: '#26262d' }}>
            <th className="py-1 pr-2">Ενότητα</th>
            <th className="py-1 w-24">Βαθμολογία</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it, idx) => (
            <tr key={`${it.label}-${idx}`} className="border-b" style={{ borderColor: '#1d1d22' }}>
              <td className="py-1 pr-2">{it.label}</td>
              <td className="py-1 font-mono">{it.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FieldScoresTable({ scores }: { scores: FieldScore[] }) {
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b text-left" style={{ borderColor: '#26262d' }}>
          <th className="py-1 pr-2 w-16">Κωδικός</th>
          <th className="py-1 pr-2">Περιγραφή</th>
          <th className="py-1 w-20">Τιμή</th>
        </tr>
      </thead>
      <tbody>
        {scores.map((s, idx) => (
          <tr key={`${s.field_code}-${idx}`} className="border-b" style={{ borderColor: '#1d1d22' }}>
            <td className="py-1 pr-2 font-mono">{s.field_code}</td>
            <td className="py-1 pr-2">{s.description}</td>
            <td className="py-1 font-mono">{String(s.value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function EntryDetails({ entry, title }: { entry: EvaluationEntry; title?: string }) {
  const evaluator = entry.evaluator
  return (
    <div className="flex flex-col gap-3">
      {title && (
        <h3 className="text-sm font-semibold" style={{ color: '#f2f2f4' }}>
          {title}
        </h3>
      )}

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm" style={{ color: '#c8c8d0' }}>
        {entry.ea_type && (
          <>
            <span style={{ color: '#8b8b95' }}>Τύπος έκθεσης</span>
            <span>{entry.ea_type}</span>
          </>
        )}
        {entry.characterization && (
          <>
            <span style={{ color: '#8b8b95' }}>Χαρακτηρισμός</span>
            <span>{entry.characterization}</span>
          </>
        )}
        {entry.score !== undefined && entry.score !== null && (
          <>
            <span style={{ color: '#8b8b95' }}>Συνολική βαθμολογία</span>
            <span className="font-mono">{entry.score}</span>
          </>
        )}
        {entry.unit && (
          <>
            <span style={{ color: '#8b8b95' }}>Μονάδα</span>
            <span>{entry.unit}</span>
          </>
        )}
        {evaluator && (evaluator.rank || evaluator.name || evaluator.role) && (
          <>
            <span style={{ color: '#8b8b95' }}>Αξιολογητής</span>
            <span>
              {[evaluator.rank, evaluator.name, evaluator.role].filter(Boolean).join(' - ')}
            </span>
          </>
        )}
      </div>

      {Array.isArray(entry.field_scores) && entry.field_scores.length > 0 && (
        <div className="flex flex-col gap-1">
          <h4 className="text-xs font-semibold uppercase" style={{ color: '#8b8b95' }}>
            Αναλυτικές βαθμολογίες
          </h4>
          <FieldScoresTable scores={entry.field_scores} />
        </div>
      )}
    </div>
  )
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

      <p className="font-mono text-xs" style={{ color: '#8b8b95' }}>
        Καταχώρηση ελέγχου: #{auditId}
      </p>
    </div>
  )
}

interface ResultsPanelProps {
  result: StructuredResult | SemanticResult | null
  auditId: number | null
}

export function ResultsPanel({ result, auditId }: ResultsPanelProps) {
  if (!result || auditId === null) {
    return <EmptyState message="Υποβάλετε ένα ερώτημα για να δείτε αποτελέσματα" />
  }

  return (
    <div className="rounded border p-4" style={{ borderColor: '#26262d', backgroundColor: '#0e0e11' }}>
      {result.mode === 'semantic' ? (
        <SemanticAnswer
          answer={result.answer}
          citations={result.citations}
          auditId={auditId}
          routingHint={result.routing_hint}
        />
      ) : (
        <StructuredView result={result} auditId={auditId} />
      )}
    </div>
  )
}