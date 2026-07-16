import type { SemanticResult, StructuredResult } from '../api/types'
import { SemanticAnswer } from './SemanticAnswer'
import { EmptyState } from './EmptyState'

interface Section {
  section: string
  score: number
  comment: string
}

function isSection(value: unknown): value is Section {
  return (
    typeof value === 'object' &&
    value !== null &&
    'section' in value &&
    'score' in value
  )
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

function StructuredView({ result, auditId }: { result: StructuredResult; auditId: number }) {
  const data = result.data
  const hasData = Object.keys(data).length > 0

  return (
    <div className="flex flex-col gap-4">
      {!hasData && <EmptyState message="Δεν βρέθηκαν βαθμολογίες στο εύρος" />}

      {Array.isArray(data.sections) && data.sections.every(isSection) && (
        <SectionsTable sections={data.sections} />
      )}

      {Array.isArray(data.sections_a) && Array.isArray(data.sections_b) && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <SectionsTable sections={data.sections_a as Section[]} title={String(data.period_a ?? 'Περίοδος Α')} />
          <SectionsTable sections={data.sections_b as Section[]} title={String(data.period_b ?? 'Περίοδος Β')} />
        </div>
      )}

      {Array.isArray(data.top) && Array.isArray(data.bottom) && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <SectionsTable sections={data.top as Section[]} title="Κορυφαίες ενότητες" />
          <SectionsTable sections={data.bottom as Section[]} title="Χαμηλότερες ενότητες" />
        </div>
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
