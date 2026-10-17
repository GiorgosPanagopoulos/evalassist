import { useEffect, useState } from 'react'
import type { ApiClient, ApiError } from '../api/client'
import type { PersonOut, TimelinePoint, TimelineResult } from '../api/types'
import type { UiFlags } from '../lib/flags'
import { DOCUMENT_UNAVAILABLE, POPUP_BLOCKED, openDocument } from '../lib/openDocument'
import { scaleDomain, timelineCsv, type ScaleMode } from '../lib/timeline'
import type { QueryMode } from './ModeBadge'
import { PeriodList } from './PeriodList'
import { PersonCard } from './PersonCard'
import { StatusFooter } from './StatusFooter'
import { TimelineChart } from './TimelineChart'

// Structural subset ώστε τα tests να περνάνε plain fake αντί για ApiClient.
// Χωρίς documentFile δεν εμφανίζεται άνοιγμα PDF, όποιο κι αν είναι το flag.
export type TimelinePanelApi = Pick<ApiClient, 'getTimeline'> & Partial<Pick<ApiClient, 'documentFile'>>

interface TimelinePanelProps {
  api: TimelinePanelApi
  // Το άτομο της αναζήτησης στο toolbar, η μόνη πηγή επιλογής ατόμου:
  // η χρονογραμμή δεν έχει δικό της dropdown ούτε δικό της state ατόμου.
  person: PersonOut | null
  mode?: QueryMode
  flags?: Pick<UiFlags, 'documentFile' | 'export'>
  // Changing it refetches the timeline for the same person.
  reloadKey?: number
}

export const NO_PERSON_TEXT = 'Επιλέξτε άτομο από την αναζήτηση'

const ENDPOINT = 'GET /api/person/{person_id}/timeline'

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  URL.revokeObjectURL(url)
}

export function TimelinePanel({ api, person, mode = 'structured', flags, reloadKey = 0 }: TimelinePanelProps) {
  const personId = person?.person_id ?? ''
  const [result, setResult] = useState<TimelineResult | null>(null)
  const [auditId, setAuditId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)
  const [scale, setScale] = useState<ScaleMode>('fixed')
  const [documentBusy, setDocumentBusy] = useState(false)
  const [documentMessage, setDocumentMessage] = useState<string | null>(null)

  // Το μήνυμα αφορά το έγγραφο που ζητήθηκε: σβήνει με νέα επιλογή ή άτομο.
  useEffect(() => setDocumentMessage(null), [selected, personId])

  const documentFile = api.documentFile?.bind(api)
  const canOpenDocument = flags?.documentFile === true && documentFile !== undefined

  async function handleOpenDocument(point: TimelinePoint) {
    if (!documentFile || documentBusy) return
    setDocumentMessage(null)
    setDocumentBusy(true)
    try {
      const outcome = await openDocument({ documentFile }, personId, point)
      if (outcome === 'unavailable') setDocumentMessage(DOCUMENT_UNAVAILABLE)
      if (outcome === 'popup_blocked') setDocumentMessage(POPUP_BLOCKED)
    } finally {
      setDocumentBusy(false)
    }
  }

  useEffect(() => {
    // Καθαρισμός πριν από κάθε νέο άτομο: η χρονογραμμή του προηγούμενου δεν
    // μένει ποτέ στην οθόνη όσο φορτώνει η επόμενη.
    setResult(null)
    setAuditId(null)
    setError(null)
    setSelected(null)
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
        const count = response.result.points.length
        setSelected(count > 0 ? count - 1 : null)
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
  }, [api, personId, reloadKey])

  const points = result && !loading ? result.points : null

  return (
    <section className="flex flex-col gap-5" aria-label="Χρονογραμμή βαθμολογίας">
      {person ? (
        <PersonCard person={person} points={points} mode={mode} />
      ) : (
        <div className="flex flex-col items-center rounded-2xl border border-dashed border-line-strong bg-card px-6 py-10 text-center">
          <img
            src={`${import.meta.env.BASE_URL}logo-watermark.png`}
            alt=""
            aria-hidden="true"
            width={160}
            height={160}
            className="mb-5 h-40 w-40 rounded-full object-cover opacity-[.18] select-none"
          />
          <p className="text-[15px] text-muted">{NO_PERSON_TEXT}</p>
          <p className="mt-1 text-[13px] text-subtle">Όνομα ή Α.Γ.Μ., συντόμευση Ctrl+K</p>
        </div>
      )}

      {error && <p className="text-[14px] text-danger-soft">{error}</p>}
      {loading && <p className="text-[13px] text-muted">Φόρτωση...</p>}

      {points && person && (
        // Side by side the chart card sets the row height and the list fills it
        // with its own scroll; the SVG is never stretched. Stacked below 880px.
        <div className="@container">
          <div className="grid gap-5 @[880px]:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
            <div className="min-w-0 rounded-2xl border border-line bg-card px-4 py-5 sm:px-6">
              <TimelineChart
                points={points}
                selected={selected}
                onSelect={setSelected}
                scale={scale}
                onScaleChange={setScale}
              />
            </div>
            <div className="relative min-w-0">
              <div className="@[880px]:absolute @[880px]:inset-0">
                <PeriodList
                  points={points}
                  selected={selected}
                  onSelect={setSelected}
                  domain={scaleDomain(scale, points)}
              onOpenDocument={canOpenDocument ? handleOpenDocument : undefined}
              documentBusy={documentBusy}
              documentMessage={documentMessage}
              onExportCsv={
                flags?.export ? () => download(`timeline-${person.person_id}.csv`, timelineCsv(person.person_id, points)) : undefined
              }
              onExportPdf={flags?.export ? () => window.print() : undefined}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      <StatusFooter
        items={
          result && !loading
            ? [
                auditId !== null ? `audit #${auditId}` : null,
                ENDPOINT,
                `έγγραφα: ${result.retrieved_doc_ids.join(', ') || '-'}`,
              ]
            : []
        }
      />
    </section>
  )
}
