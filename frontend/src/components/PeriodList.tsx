import { useEffect, useRef, useState } from 'react'
import type { TimelinePoint } from '../api/types'
import { copyText } from '../lib/clipboard'
import { citationText, formatScore, periodLabel, periodParts, timelineStats } from '../lib/timeline'
import { CopyIcon, DownloadIcon, ExternalIcon, FlagIcon } from './icons'

interface PeriodListProps {
  points: TimelinePoint[]
  selected: number | null
  onSelect: (index: number) => void
  // Same y domain as the chart, so bars follow its scale and zoom.
  domain: [number, number]
  // Each action is offered only when its handler is given (feature flags).
  onOpenDocument?: (point: TimelinePoint) => void
  // Ένα άνοιγμα τη φορά: όσο τρέχει, τα κουμπιά ανοίγματος είναι disabled.
  documentBusy?: boolean
  documentMessage?: string | null
  onFlag?: (point: TimelinePoint) => void
  onExportCsv?: () => void
  onExportPdf?: () => void
}

function barShare(score: number, [lo, hi]: [number, number]): number {
  return Math.max(0, Math.min(1, (score - lo) / (hi - lo)))
}

export function PeriodList({
  points,
  selected,
  onSelect,
  domain,
  onOpenDocument,
  documentBusy = false,
  documentMessage = null,
  onFlag,
  onExportCsv,
  onExportPdf,
}: PeriodListProps) {
  const listRef = useRef<HTMLOListElement>(null)
  const [copied, setCopied] = useState<'ok' | 'fail' | null>(null)
  const stats = timelineStats(points)
  // Newest first; indexes stay those of `points`.
  const order = points.map((_, i) => i).reverse()
  const current = selected === null ? null : points[selected] ?? null

  useEffect(() => {
    if (selected === null) return
    const row = listRef.current?.querySelector<HTMLElement>(`[data-index="${selected}"]`)
    row?.scrollIntoView?.({ block: 'nearest' })
  }, [selected])

  useEffect(() => setCopied(null), [selected])

  async function handleCopy() {
    if (!current) return
    setCopied((await copyText(citationText(current))) ? 'ok' : 'fail')
  }

  return (
    <div className="flex h-full min-h-0 flex-col rounded-2xl border border-line bg-card">
      <div className="flex min-h-[68px] items-center justify-between gap-3 border-b border-line px-5">
        <h3 className="text-[17px] font-semibold text-ink">Περίοδοι</h3>
        {(onExportCsv || onExportPdf) && (
          <div className="flex gap-2">
            {onExportCsv && (
              <button
                type="button"
                onClick={onExportCsv}
                className="no-print inline-flex h-11 items-center gap-1.5 rounded-lg border border-line-strong px-3 text-[13px] text-ink hover:border-gold"
              >
                <DownloadIcon size={15} />
                CSV
              </button>
            )}
            {onExportPdf && (
              <button
                type="button"
                onClick={onExportPdf}
                className="no-print inline-flex h-11 items-center gap-1.5 rounded-lg border border-line-strong px-3 text-[13px] text-ink hover:border-gold"
              >
                <DownloadIcon size={15} />
                PDF
              </button>
            )}
          </div>
        )}
      </div>

      <ol ref={listRef} aria-label="Λίστα περιόδων" className="max-h-[420px] min-h-0 flex-1 overflow-y-auto @[880px]:max-h-none">
        {order.map((i) => {
          const p = points[i]
          const isSelected = selected === i
          const isMin = p.score !== null && p.score === stats.min
          const label = periodLabel(p)
          const parts = periodParts(p)
          return (
            <li
              key={`${p.period}-${i}`}
              data-index={i}
              className={`flex items-center border-b border-l-[3px] border-b-line ${
                isSelected ? 'border-l-gold bg-navy' : 'border-l-transparent'
              }`}
            >
              <button
                type="button"
                onClick={() => onSelect(i)}
                aria-pressed={isSelected}
                aria-label={`${label}, ${p.kind}, ${p.score === null ? 'χωρίς βαθμό' : `βαθμός ${formatScore(p.score)}`}`}
                className="flex min-h-12 min-w-0 flex-1 items-center gap-3 py-2 pr-2 pl-4 text-left"
              >
                <span className="flex w-[112px] shrink-0 flex-col">
                  <span className={`text-[14px] text-ink ${isSelected || parts.range ? 'font-semibold' : ''}`}>
                    {parts.title}
                  </span>
                  {parts.range && (
                    <span className="font-mono text-[11px] leading-snug text-muted">
                      <span className="whitespace-nowrap">{parts.range[0]}</span>
                      {' - '}
                      <span className="whitespace-nowrap">{parts.range[1]}</span>
                    </span>
                  )}
                </span>
                {p.score === null ? (
                  <span className="flex-1 text-[13px] text-muted">Σ.Α. · χωρίς βαθμό</span>
                ) : (
                  <>
                    <span className="h-1.5 min-w-10 flex-1 overflow-hidden rounded-full bg-line" aria-hidden="true">
                      <span
                        data-testid="score-bar"
                        className={`block h-full rounded-full ${isMin ? 'bg-danger-soft' : 'bg-gold'}`}
                        style={{ width: `${barShare(p.score, domain) * 100}%` }}
                      />
                    </span>
                    <span
                      className={`w-10 shrink-0 text-right text-[17px] font-semibold ${
                        isMin ? 'text-danger-soft' : 'text-ink'
                      }`}
                    >
                      {formatScore(p.score)}
                    </span>
                  </>
                )}
              </button>
              {onOpenDocument && (
                <button
                  type="button"
                  onClick={() => onOpenDocument(p)}
                  disabled={documentBusy}
                  aria-label={`Άνοιγμα PDF ${label}, σελίδα ${p.page ?? 1}`}
                  className="mr-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted hover:text-gold disabled:opacity-50"
                >
                  <ExternalIcon size={17} />
                </button>
              )}
            </li>
          )
        })}
      </ol>

      <div className="no-print flex flex-col gap-2.5 border-t border-line p-4">
        {onOpenDocument && current && (
          <button
            type="button"
            onClick={() => onOpenDocument(current)}
            disabled={documentBusy}
            className="flex min-h-12 items-center justify-center rounded-lg bg-gold px-4 text-[15px] font-semibold text-bg hover:bg-gold-hover disabled:opacity-50"
          >
            {current.page === null ? 'Άνοιγμα PDF' : `Άνοιγμα PDF στη σελίδα ${current.page}`}
          </button>
        )}
        {onOpenDocument && (
          <p data-testid="document-message" aria-live="polite" className="min-h-[1em] text-[13px] text-danger-soft">
            {documentMessage}
          </p>
        )}
        <div className="flex gap-2.5">
          <button
            type="button"
            onClick={handleCopy}
            disabled={!current}
            className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-lg border border-line-strong px-3 text-[14px] text-ink hover:border-gold disabled:opacity-50"
          >
            <CopyIcon size={15} />
            Αντιγραφή παραπομπής
          </button>
          {onFlag && (
            <button
              type="button"
              onClick={() => current && onFlag(current)}
              disabled={!current}
              className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-lg border border-gold/60 px-3 text-[14px] font-semibold text-gold hover:border-gold disabled:opacity-50"
            >
              <FlagIcon size={15} />
              Σήμανση για έλεγχο
            </button>
          )}
        </div>
        {current && (
          <p
            data-testid="selected-citation"
            title={citationText(current)}
            className="truncate font-mono text-[12px] text-muted"
          >
            {citationText(current)}
          </p>
        )}
        <p role="status" className="min-h-[1em] text-[12px] text-ok-text">
          {copied === 'ok' && 'Η παραπομπή αντιγράφηκε'}
          {copied === 'fail' && <span className="text-danger-soft">Η αντιγραφή απέτυχε</span>}
        </p>
      </div>
    </div>
  )
}
