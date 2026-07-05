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
      {title && <h3 className="text-sm font-semibold text-navy dark:text-gold">{title}</h3>}
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-navy/20 text-left dark:border-gold/20">
            <th className="py-1">Ενότητα</th>
            <th className="py-1">Βαθμολογία</th>
            <th className="py-1">Σχόλιο</th>
          </tr>
        </thead>
        <tbody>
          {sections.map((s, idx) => (
            <tr key={`${s.section}-${idx}`} className="border-b border-navy/10 dark:border-gold/10">
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

      <p className="font-mono text-xs text-navy/60 dark:text-gold/60">Καταχώρηση ελέγχου: #{auditId}</p>
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
    <div className="rounded border border-navy/20 bg-white p-4 dark:border-gold/20 dark:bg-navy">
      {result.mode === 'semantic' ? (
        <SemanticAnswer answer={result.answer} citations={result.citations} auditId={auditId} />
      ) : (
        <StructuredView result={result} auditId={auditId} />
      )}
    </div>
  )
}
