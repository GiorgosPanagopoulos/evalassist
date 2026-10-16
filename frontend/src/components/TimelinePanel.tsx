import { useEffect, useState } from 'react'
import type { ApiClient, ApiError } from '../api/client'
import type { PersonOut, TimelineResult } from '../api/types'
import { PersonHeading } from './PersonHeading'
import { TimelineChart } from './TimelineChart'

// Structural subset ώστε τα tests να περνάνε plain fake αντί για ApiClient.
export type TimelinePanelApi = Pick<ApiClient, 'getTimeline'>

interface TimelinePanelProps {
  api: TimelinePanelApi
  // Το άτομο του αριστερού πάνελ (QueryForm), η μόνη πηγή επιλογής ατόμου:
  // η χρονογραμμή δεν έχει δικό της dropdown ούτε δικό της state ατόμου.
  person: PersonOut | null
}

const LABEL_CLASS = 'text-[11px] font-semibold uppercase tracking-[.6px] text-[#8b8b95]'

export const NO_PERSON_TEXT = 'Επιλέξτε άτομο από αριστερά'

export function TimelinePanel({ api, person }: TimelinePanelProps) {
  const personId = person?.person_id ?? ''
  const [result, setResult] = useState<TimelineResult | null>(null)
  const [auditId, setAuditId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    // Καθαρισμός πριν από κάθε νέο άτομο: η χρονογραμμή του προηγούμενου δεν
    // μένει ποτέ στην οθόνη όσο φορτώνει η επόμενη.
    setResult(null)
    setAuditId(null)
    setError(null)
    if (!personId) {
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    api
      .getTimeline(personId)
      .then((response) => {
        if (cancelled) return
        setResult(response.result)
        setAuditId(response.audit_id)
      })
      .catch((err: ApiError) => {
        if (cancelled) return
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
      <div className="flex flex-col gap-1">
        <span className={LABEL_CLASS}>Χρονογραμμή βαθμολογίας</span>
        <span className="font-mono text-[11px]" style={{ color: '#6d6d78' }}>
          structured · χωρίς LLM · GET /api/person/{'{person_id}'}/timeline
        </span>
      </div>

      {person ? (
        <PersonHeading person={person} testId="timeline-person" />
      ) : (
        <p className="text-[13px]" style={{ color: '#6d6d78' }}>
          {NO_PERSON_TEXT}
        </p>
      )}

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
    </section>
  )
}
