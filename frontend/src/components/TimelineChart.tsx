import { useEffect, useId, useRef, useState } from 'react'
import type { TimelinePoint } from '../api/types'
import {
  deltaFromPrevious,
  formatDelta,
  formatScore,
  pageText,
  periodLabel,
  periodMid,
  periodRange,
  scaleDomain,
  timelineStats,
  FIXED_FLOOR,
  type ScaleMode,
} from '../lib/timeline'

// Plain SVG, no chart library. Σ.Α. (score === null) are shaded bands: they
// get no y, are never joined by a line, and split the Ε.Α. polyline around
// them. No interpolation in the frontend.

const SCALES: { value: ScaleMode; label: string }[] = [
  { value: 'fixed', label: '80-100' },
  { value: 'full', label: '0-100' },
  { value: 'zoom', label: 'Μεγέθυνση' },
]

const GOLD = '#d4a93a'
const BAND_FILL = 'rgba(201,162,39,0.10)'
const BAND_STROKE = 'rgba(201,162,39,0.30)'
const DANGER = '#f2a48f'
const GRID = '#1e2a44'
const AXIS = '#2a3756'
const MUTED = '#a9b4c8'
const CARD = '#0f1a2f'

const DEFAULT_WIDTH = 960

function useWidth<T extends HTMLElement>(active: boolean) {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(DEFAULT_WIDTH)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.round(entry.contentRect.width)
      if (next > 0) setWidth(next)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [active])
  return [ref, width] as const
}

interface Box {
  x: number
  y: number
  w: number
  h: number
}

function overlap(a: Box, b: Box): number {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
  return w > 0 && h > 0 ? w * h : 0
}

const TIP_W = 260
const TIP_H = 150
const TIP_GAP = 14

// Above the point when it fits, else below, clamped at the edges; beside it
// when both would hide the point, its neighbours or the min label. Ties keep
// that order.
function placeTip(x: number, y: number, width: number, height: number, obstacles: Box[]): { left: number; top: number } {
  const w = Math.min(TIP_W, width - 8)
  const centered = Math.max(4, Math.min(x - w / 2, width - w - 4))
  const above = y - TIP_GAP - TIP_H
  const below = y + TIP_GAP
  const middle = Math.max(0, Math.min(y - TIP_H / 2, height - TIP_H))
  const lefts = [centered, x + TIP_GAP, x - TIP_GAP - w]
  const tops = [above, below, middle, 0, height - TIP_H]
  const candidates = [
    { left: centered, top: above },
    { left: centered, top: below },
    ...lefts.slice(1).flatMap((left) => tops.slice(2).map((top) => ({ left, top }))),
    ...lefts.slice(1).flatMap((left) => [above, below].map((top) => ({ left, top }))),
  ].filter((c) => c.top >= 0 && c.top + TIP_H <= height && c.left >= 0 && c.left + w <= width)
  if (candidates.length === 0) return { left: centered, top: Math.max(0, Math.min(y + TIP_GAP, height - TIP_H)) }
  const cost = (c: { left: number; top: number }) =>
    obstacles.reduce((sum, o) => sum + overlap({ x: c.left, y: c.top, w, h: TIP_H }, o), 0)
  return candidates.reduce((best, c) => (cost(c) < cost(best) ? c : best))
}

function yTicks(lo: number, hi: number): number[] {
  const span = hi - lo
  const step = span <= 6 ? 1 : span <= 12 ? 2 : span <= 30 ? 5 : 20
  const ticks: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) ticks.push(v)
  return ticks
}

interface Placed {
  point: TimelinePoint
  index: number
  x: number
  x0: number
  x1: number
  y: number | null
}

export interface TimelineChartProps {
  points: TimelinePoint[]
  selected?: number | null
  onSelect?: (index: number) => void
  // Controlled by the panel so the period list bars use the same domain.
  scale?: ScaleMode
  onScaleChange?: (scale: ScaleMode) => void
}

export function TimelineChart({ points, selected = null, onSelect, scale: scaleProp, onScaleChange }: TimelineChartProps) {
  const [ownScale, setOwnScale] = useState<ScaleMode>('fixed')
  const scale = scaleProp ?? ownScale
  const setScale = (next: ScaleMode) => {
    setOwnScale(next)
    onScaleChange?.(next)
  }
  const [hover, setHover] = useState<number | null>(null)
  const [boxRef, width] = useWidth<HTMLDivElement>(points.length > 0)
  const scaleLabelId = useId()

  if (points.length === 0) {
    return <p className="text-[14px] text-muted">Καμία αξιολόγηση για το επιλεγμένο άτομο.</p>
  }

  const narrow = width < 560
  const height = narrow ? 260 : 340
  const margin = { top: 26, right: 14, bottom: 30, left: 38 }
  const plotW = Math.max(width - margin.left - margin.right, 10)
  const plotH = height - margin.top - margin.bottom

  const ranges = points.map(periodRange)
  const tMin = Math.min(...ranges.map((r) => r.start))
  const tMax = Math.max(...ranges.map((r) => r.end))
  const tSpan = Math.max(tMax - tMin, 1)
  const xOf = (t: number) => margin.left + ((t - tMin) / tSpan) * plotW

  const [lo, hi] = scaleDomain(scale, points)
  const extended = scale === 'fixed' && lo < FIXED_FLOOR
  const yOf = (s: number) => margin.top + ((hi - s) / (hi - lo)) * plotH

  const stats = timelineStats(points)

  const placed: Placed[] = points.map((point, index) => ({
    point,
    index,
    x: xOf(periodMid(point)),
    x0: xOf(ranges[index].start),
    x1: xOf(ranges[index].end),
    y: point.score === null ? null : yOf(point.score),
  }))

  // One polyline per run of scored periods; any Σ.Α. ends the run.
  const segments: Placed[][] = []
  let run: Placed[] = []
  for (const p of placed) {
    if (p.y === null) {
      if (run.length > 0) segments.push(run)
      run = []
    } else {
      run.push(p)
    }
  }
  if (run.length > 0) segments.push(run)

  const firstYear = new Date(tMin).getUTCFullYear()
  const lastYear = new Date(tMax).getUTCFullYear()
  const maxTicks = Math.max(2, Math.floor(plotW / (narrow ? 56 : 72)))
  const yearStep = Math.max(1, Math.ceil((lastYear - firstYear + 1) / maxTicks))
  const yearTicks: number[] = []
  for (let y = firstYear; y <= lastYear + 1; y += 1) {
    const t = Date.UTC(y, 0, 1)
    if (t >= tMin && t <= tMax && (y - firstYear) % yearStep === 0) yearTicks.push(t)
  }

  const minIndex = stats.min === null ? -1 : points.findIndex((p) => p.score === stats.min)
  const gapCount = placed.filter((p) => p.y === null).length
  const tip = hover === null ? null : placed[hover]
  const delta = tip ? deltaFromPrevious(points, tip.index) : null
  // Below the min point, or beside it when the point sits on the x axis.
  let minLabel: { x: number; y: number; anchor: 'middle' | 'start' } | null = null
  if (minIndex >= 0 && placed[minIndex].y !== null) {
    const { x, y } = placed[minIndex] as { x: number; y: number }
    minLabel =
      y + 22 <= height - margin.bottom - 4 ? { x, y: y + 22, anchor: 'middle' } : { x: x + 10, y: y - 8, anchor: 'start' }
  }
  let tipPos: { left: number; top: number } | null = null
  if (tip) {
    const obstacles: Box[] = placed
      .filter((p) => p.y !== null)
      .map((p) => ({ x: p.x - 8, y: (p.y as number) - 8, w: 16, h: 16 }))
    if (minLabel) {
      const lx = minLabel.anchor === 'middle' ? minLabel.x - 34 : minLabel.x
      obstacles.push({ x: lx, y: minLabel.y - 12, w: 68, h: 16 })
    }
    tipPos = narrow ? null : placeTip(tip.x, tip.y ?? margin.top + plotH / 2, width, height, obstacles)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-[17px] font-semibold text-ink">Χρονογραμμή βαθμολογίας</h3>
        <div className="flex flex-wrap items-center gap-3">
          {extended && (
            <span data-testid="scale-extended" role="status" className="text-[12px] text-danger-soft">
              Κλίμακα επεκτάθηκε σε {lo}-100
            </span>
          )}
          <span className="text-[13px] text-muted" id={scaleLabelId}>
            Κλίμακα
          </span>
          <div
            role="group"
            aria-labelledby={scaleLabelId}
            className="flex overflow-hidden rounded-lg bg-input ring-1 ring-line-strong"
          >
            {SCALES.map((s) => (
              <button
                key={s.value}
                type="button"
                aria-pressed={scale === s.value}
                onClick={() => setScale(s.value)}
                className={`h-11 px-3 text-[13px] font-semibold ${
                  scale === s.value ? 'bg-navy text-ink' : 'text-muted hover:text-ink'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div ref={boxRef} className="relative" onMouseLeave={() => setHover(null)}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width="100%"
          height={height}
          role="img"
          aria-label={`Χρονογραμμή βαθμολογίας: ${placed.length} περίοδοι, ${gapCount} Σ.Α. χωρίς βαθμό, άξονας Y ${lo}-${hi}`}
          style={{ display: 'block', fontFamily: 'var(--font-mono)' }}
        >
          {yTicks(lo, hi).map((v) => (
            <g key={v}>
              <line x1={margin.left} x2={width - margin.right} y1={yOf(v)} y2={yOf(v)} stroke={GRID} />
              <text x={margin.left - 8} y={yOf(v) + 4} textAnchor="end" fontSize="11" fill={MUTED}>
                {v}
              </text>
            </g>
          ))}

          <line x1={margin.left} x2={margin.left} y1={margin.top} y2={height - margin.bottom} stroke={AXIS} />
          <line
            x1={margin.left}
            x2={width - margin.right}
            y1={height - margin.bottom}
            y2={height - margin.bottom}
            stroke={AXIS}
          />
          {lo > 0 && (
            // Axis break: the y axis does not start at 0.
            <g data-testid="axis-break" transform={`translate(${margin.left}, ${height - margin.bottom - 10})`}>
              <polyline points="-4,0 4,3 -4,6 4,9" fill="none" stroke={MUTED} strokeWidth="1.2" />
            </g>
          )}

          {yearTicks.map((t) => (
            <text
              key={t}
              x={xOf(t)}
              y={height - margin.bottom + 18}
              textAnchor="middle"
              fontSize="11"
              fill={MUTED}
            >
              {new Date(t).getUTCFullYear()}
            </text>
          ))}

          {placed
            .filter((p) => p.y === null)
            .map((p) => {
              const w = Math.max(p.x1 - p.x0, 5)
              const on = selected === p.index || hover === p.index
              const showLabel = w >= 22 || !narrow
              return (
                <g
                  key={p.index}
                  data-testid="sa-gap"
                  data-selected={selected === p.index || undefined}
                  onMouseEnter={() => setHover(p.index)}
                  onClick={() => onSelect?.(p.index)}
                  style={{ cursor: 'pointer' }}
                >
                  <title>{`${p.point.kind} ${periodLabel(p.point)} · χωρίς βαθμολογία`}</title>
                  <rect
                    x={p.x - w / 2}
                    y={margin.top}
                    width={w}
                    height={plotH}
                    fill={BAND_FILL}
                    stroke={on ? GOLD : BAND_STROKE}
                    strokeWidth="1"
                  />
                  {showLabel && (
                    <text x={p.x} y={margin.top - 6} textAnchor="middle" fontSize="10" fill={MUTED}>
                      Σ.Α.
                    </text>
                  )}
                </g>
              )
            })}

          {stats.mean !== null && (
            <line
              data-testid="mean-line"
              x1={margin.left}
              x2={width - margin.right}
              y1={yOf(stats.mean)}
              y2={yOf(stats.mean)}
              stroke={MUTED}
              strokeOpacity={0.7}
              strokeDasharray="5 4"
            />
          )}

          {selected !== null && placed[selected] && (
            <line
              x1={placed[selected].x}
              x2={placed[selected].x}
              y1={margin.top}
              y2={height - margin.bottom}
              stroke={AXIS}
            />
          )}

          {segments.map((seg, i) => (
            <polyline
              key={i}
              data-testid="ea-segment"
              points={seg.map((p) => `${p.x.toFixed(1)},${(p.y as number).toFixed(1)}`).join(' ')}
              fill="none"
              stroke={GOLD}
              strokeWidth="2"
              strokeLinejoin="round"
            />
          ))}

          {placed
            .filter((p) => p.y !== null)
            .map((p) => {
              const isMin = p.index === minIndex
              const isSelected = selected === p.index
              const color = isMin ? DANGER : GOLD
              return (
                <g
                  key={p.index}
                  data-testid="ea-point"
                  data-selected={isSelected || undefined}
                  onMouseEnter={() => setHover(p.index)}
                  onClick={() => onSelect?.(p.index)}
                  style={{ cursor: 'pointer' }}
                >
                  <circle cx={p.x} cy={p.y as number} r="12" fill="transparent" />
                  <circle
                    cx={p.x}
                    cy={p.y as number}
                    r={isSelected ? 6.5 : 4.5}
                    fill={isSelected ? color : CARD}
                    stroke={color}
                    strokeWidth="2"
                  />
                </g>
              )
            })}

          {minLabel && (
            <text
              data-testid="min-marker"
              x={minLabel.x}
              y={minLabel.y}
              textAnchor={minLabel.anchor}
              fontSize="11"
              fill={DANGER}
            >
              ελάχ. {formatScore(stats.min as number)}
            </text>
          )}
        </svg>

        {tip && (
          // Narrow screens: a panel under the plot instead of a floating box,
          // so it never hides points.
          <div
            data-testid="timeline-tooltip"
            role="tooltip"
            className={`pointer-events-none rounded-xl border border-line-strong bg-navy px-4 py-3 ${
              tipPos ? 'absolute z-10 shadow-[0_12px_32px_rgba(0,0,0,.45)]' : 'mt-3'
            }`}
            style={tipPos ? { left: tipPos.left, top: tipPos.top, width: Math.min(TIP_W, width - 8), minHeight: TIP_H } : undefined}
          >
            <div className="flex items-center justify-between gap-3 text-[13px] text-muted">
              <span>
                {periodLabel(tip.point)} · {tip.point.kind}
              </span>
              {delta !== null && (
                <span
                  className={`font-mono ${delta < 0 ? 'text-danger-soft' : delta > 0 ? 'text-ok-text' : 'text-muted'}`}
                  aria-label={`Δ από προηγούμενο ${formatDelta(delta)}`}
                >
                  Δ {formatDelta(delta)}
                </span>
              )}
            </div>
            <p className="mt-1 text-[28px] leading-tight font-bold text-ink">
              {tip.point.score === null ? 'χωρίς βαθμό' : formatScore(tip.point.score)}
            </p>
            <p className="mt-1 font-mono text-[12px] text-ink">
              {tip.point.doc_id} · {pageText(tip.point.page)}
            </p>
            <p className="line-clamp-2 font-mono text-[12px] text-ink">{tip.point.section}</p>
            <p className="mt-1 text-[12px] text-muted">Κλικ για επιλογή περιόδου</p>
          </div>
        )}
      </div>

      <ul className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px] text-muted" aria-label="Υπόμνημα">
        <li className="inline-flex items-center gap-2">
          <svg width="18" height="10" aria-hidden>
            <line x1="0" y1="5" x2="18" y2="5" stroke={GOLD} strokeWidth="2" />
          </svg>
          Ε.Α. βαθμός
        </li>
        {stats.mean !== null && (
          <li className="inline-flex items-center gap-2">
            <svg width="18" height="10" aria-hidden>
              <line x1="0" y1="5" x2="18" y2="5" stroke={MUTED} strokeWidth="1.5" strokeDasharray="4 3" />
            </svg>
            Μέσος {formatScore(stats.mean)}
          </li>
        )}
        <li className="inline-flex items-center gap-2">
          <svg width="12" height="12" aria-hidden>
            <rect x="0.5" y="0.5" width="11" height="11" fill={BAND_FILL} stroke={BAND_STROKE} />
          </svg>
          Σ.Α. χωρίς βαθμό ({gapCount})
        </li>
        {stats.min !== null && (
          <li className="inline-flex items-center gap-2">
            <svg width="12" height="12" aria-hidden>
              <circle cx="6" cy="6" r="4" fill={CARD} stroke={DANGER} strokeWidth="2" />
            </svg>
            Ελάχιστο {formatScore(stats.min)}
          </li>
        )}
      </ul>
    </div>
  )
}
