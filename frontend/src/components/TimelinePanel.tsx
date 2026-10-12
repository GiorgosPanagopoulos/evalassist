import { useEffect, useState } from 'react'
import type { ApiClient, ApiError } from '../api/client'
import type { PersonOut, TimelineResult } from '../api/types'
import { TimelineChart } from './TimelineChart'

// Structural subset ώστε τα tests να περνάνε plain fake αντί για ApiClient.
export type TimelinePanelApi = Pick<ApiClient, 'getPersons' | 'getTimeline'>

interface TimelinePanelProps {
  api: TimelinePanelApi
}

const LABEL_CLASS = 'text-[11px] font-semibold uppercase tracking-[.6px] text-[#8b8b95]'

const SELECT_CLASS =
  'rounded-lg border border-[#26262d] py-2 pl-3 pr-8 text-[13px] appearance-none bg-no-repeat bg-[right_12px_center]'

const CHEVRON_BG = {
  backgroundImage:
    "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6' fill='none'%3E%3Cpath d='M1 1L5 5L9 1' stroke='%234a4a55' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")",
}

export function TimelinePanel({ api }: TimelinePanelProps) {
  const [persons, setPersons] = useState<PersonOut[]>([])
  const [personId, setPersonId] = useState('')
  const [result, setResult] = useState<TimelineResult | null>(null)
  const [auditId, setAuditId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.getPersons().then(setPersons)
  }, [api])

  useEffect(() => {
    if (!personId) {
      setResult(null)
      setAuditId(null)
      setError(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    api
      .getTimeline(personId)
      .then((response) => {
        if (cancelled) return
        setResult(response.result)
        setAuditId(response.audit_id)
      })
      .catch((err: ApiError) => {
        if (cancelled) return
        setResult(null)
        setAuditId(null)
        setError(err.detail ?? 'Σφάλμα')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [api, personId])

  const scored = result ? result.points.filter((p) => p.score !== null).length : 0
  const unscored = result ? result.points.length - scored : 0

  return (
    <section
      className="flex flex-col gap-4 rounded-xl border"
      style={{ borderColor: '#1d1d22', backgroundColor: 'rgba(14,14,17,.85)', padding: '18px 20px' }}
      aria-label="Χρονογραμμή βαθμολογίας"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className={LABEL_CLASS}>Χρονογραμμή βαθμολογίας</span>
          <span className="font-mono text-[11px]" style={{ color: '#6d6d78' }}>
            structured · χωρίς LLM · GET /person/{'{person_id}'}/timeline
          </span>
        </div>
        <label className="flex items-center gap-2">
          <span className={LABEL_CLASS}>Άτομο</span>
          <select
            aria-label="Άτομο χρονογραμμής"
            value={personId}
            onChange={(e) => setPersonId(e.target.value)}
            className={SELECT_CLASS}
            style={{ backgroundColor: '#131318', color: personId ? '#f2f2f4' : '#6d6d78', ...CHEVRON_BG }}
          >
            <option value="">Επιλέξτε άτομο</option>
            {persons.map((p) => (
              <option key={p.person_id} value={p.person_id}>
                {p.name ? `${p.name} (${p.person_id})` : `(${p.person_id})`}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && (
        <p className="text-sm" style={{ color: '#ff6b6b' }}>
          {error}
        </p>
      )}
      {loading && (
        <p className="text-[12px]" style={{ color: '#8b8b95' }}>
          Φόρτωση...
        </p>
      )}

      {result && !loading && (
        <>
          <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px]" style={{ color: '#8b8b95' }}>
            <span>
              {result.points.length} περίοδοι · {scored} με βαθμό · {unscored} Σ.Α. χωρίς βαθμό
            </span>
            {auditId !== null && <span>audit #{auditId}</span>}
            <span>έγγραφα: {result.retrieved_doc_ids.join(', ') || '—'}</span>
          </div>
          <TimelineChart points={result.points} />
        </>
      )}

      {!personId && !loading && (
        <p className="text-[13px]" style={{ color: '#6d6d78' }}>
          Επιλέξτε άτομο για να δείτε τη χρονογραμμή.
        </p>
      )}
    </section>
  )
}
