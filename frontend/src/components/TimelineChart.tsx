import { useState } from 'react'
import type { TimelinePoint } from '../api/types'

// Plain SVG — καμία chart library. Τα Σ.Α. (score === null) σχεδιάζονται ως
// labeled gaps: δεν παίρνουν y, δεν ενώνονται ποτέ με γραμμή, και σπάνε την
// polyline των Ε.Α. γύρω τους. Καμία interpolation στο frontend.

const Y_MIN_DEFAULT = 93
const Y_MAX = 100

const WIDTH = 960
const HEIGHT = 340
const MARGIN = { top: 34, right: 24, bottom: 56, left: 52 }

const COLOR_EA = '#e8c34a'
const COLOR_SA = '#8b8b95'
const COLOR_AXIS = '#3a3a44'
const COLOR_GRID = '#1d1d22'
const COLOR_TEXT = '#8b8b95'
const COLOR_TEXT_STRONG = '#f2f2f4'
const COLOR_ACTIVE = '#4de3ff'

const DAY_MS = 24 * 60 * 60 * 1000

function periodMid(point: TimelinePoint): number {
  const [start, end] = point.period.split('..')
  const s = Date.parse(start)
  const e = Date.parse(end)
  if (Number.isNaN(s)) return NaN
  return Number.isNaN(e) ? s : (s + e) / 2
}

interface Placed {
  point: TimelinePoint
  index: number
  x: number
  y: number | null
}

export interface TimelineChartProps {
  points: TimelinePoint[]
}

export function TimelineChart({ points }: TimelineChartProps) {
  const [active, setActive] = useState<number | null>(null)

  if (points.length === 0) {
    return (
      <p className="text-[13px]" style={{ color: COLOR_TEXT }}>
        Καμία αξιολόγηση για το επιλεγμένο άτομο.
      </p>
    )
  }

  const times = points.map(periodMid)
  const tMin = Math.min(...times)
  const tMax = Math.max(...times)
  const tSpan = Math.max(tMax - tMin, 30 * DAY_MS)

  const scores = points.map((p) => p.score).filter((s): s is number => s !== null)
  // Ο άξονας είναι πάντα περικομμένος στο 93-100. Αν υπάρξει score < 93 δεν
  // κόβεται εκτός καμβά — ο άξονας κατεβαίνει, δεν αλλοιώνεται η τιμή.
  const yMin = Math.min(Y_MIN_DEFAULT, ...scores)

  const plotW = WIDTH - MARGIN.left - MARGIN.right
  const plotH = HEIGHT - MARGIN.top - MARGIN.bottom
  const xOf = (t: number) => MARGIN.left + ((t - tMin) / tSpan) * plotW
  const yOf = (s: number) => MARGIN.top + ((Y_MAX - s) / (Y_MAX - yMin)) * plotH

  const placed: Placed[] = points.map((point, index) => ({
    point,
    index,
    x: xOf(times[index]),
    y: point.score === null ? null : yOf(point.score),
  }))

  // Segments: συνεχόμενα Ε.Α. με score. Ένα Σ.Α. (ή οποιοδήποτε null) κλείνει
  // το τρέχον segment, ώστε η γραμμή να μην περνάει ποτέ πάνω από κενό.
  const segments: Placed[][] = []
  let current: Placed[] = []
  for (const p of placed) {
    if (p.y === null) {
      if (current.length > 0) segments.push(current)
      current = []
    } else {
      current.push(p)
    }
  }
  if (current.length > 0) segments.push(current)

  const yTicks: number[] = []
  for (let v = yMin; v <= Y_MAX; v += 1) yTicks.push(v)

  const firstYear = new Date(tMin).getUTCFullYear()
  const lastYear = new Date(tMax).getUTCFullYear()
  const yearTicks: number[] = []
  for (let y = firstYear; y <= lastYear; y += 1) {
    const t = Date.UTC(y, 0, 1)
    if (t >= tMin && t <= tMax) yearTicks.push(t)
  }

  const activePoint = active === null ? null : placed[active]
  const gapCount = placed.filter((p) => p.y === null).length

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px]" style={{ color: COLOR_TEXT }}>
        <span className="inline-flex items-center gap-1.5">
          <svg width="14" height="10" aria-hidden>
            <line x1="0" y1="5" x2="14" y2="5" stroke={COLOR_EA} strokeWidth="1.5" />
            <circle cx="7" cy="5" r="3" fill={COLOR_EA} />
          </svg>
          Ε.Α. — βαθμός γενικής ικανότητας
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width="14" height="10" aria-hidden>
            <line x1="7" y1="0" x2="7" y2="10" stroke={COLOR_SA} strokeWidth="1.5" strokeDasharray="2 2" />
          </svg>
          Σ.Α. — χωρίς βαθμολογία (κενό, {gapCount})
        </span>
        <span style={{ color: '#e8c34a' }}>
          ⚠ Περικομμένος άξονας Y: εμφανίζεται μόνο το {yMin}-{Y_MAX} της κλίμακας 0-100
        </span>
      </div>

      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
        role="img"
        aria-label={`Χρονογραμμή βαθμολογίας: ${placed.length} περίοδοι, ${gapCount} Σ.Α. χωρίς βαθμό`}
        style={{ display: 'block', fontFamily: 'var(--font-mono)' }}
        onMouseLeave={() => setActive(null)}
      >
        {/* grid + y ticks */}
        {yTicks.map((v) => (
          <g key={v}>
            <line
              x1={MARGIN.left}
              x2={WIDTH - MARGIN.right}
              y1={yOf(v)}
              y2={yOf(v)}
              stroke={COLOR_GRID}
              strokeWidth="1"
            />
            <text x={MARGIN.left - 10} y={yOf(v) + 4} textAnchor="end" fontSize="11" fill={COLOR_TEXT}>
              {v}
            </text>
          </g>
        ))}

        {/* y axis με σήμανση διακοπής (axis break) στο κάτω άκρο */}
        <line
          x1={MARGIN.left}
          x2={MARGIN.left}
          y1={MARGIN.top}
          y2={HEIGHT - MARGIN.bottom}
          stroke={COLOR_AXIS}
          strokeWidth="1"
        />
        <g data-testid="axis-break" transform={`translate(${MARGIN.left}, ${HEIGHT - MARGIN.bottom + 6})`}>
          <polyline points="-5,0 5,4 -5,8 5,12" fill="none" stroke={COLOR_EA} strokeWidth="1.5" />
          <text x="-10" y="26" textAnchor="end" fontSize="10" fill={COLOR_EA}>
            0
          </text>
        </g>

        {/* x axis + year ticks */}
        <line
          x1={MARGIN.left}
          x2={WIDTH - MARGIN.right}
          y1={HEIGHT - MARGIN.bottom}
          y2={HEIGHT - MARGIN.bottom}
          stroke={COLOR_AXIS}
          strokeWidth="1"
        />
        {yearTicks.map((t) => (
          <g key={t}>
            <line
              x1={xOf(t)}
              x2={xOf(t)}
              y1={HEIGHT - MARGIN.bottom}
              y2={HEIGHT - MARGIN.bottom + 5}
              stroke={COLOR_AXIS}
            />
            <text
              x={xOf(t)}
              y={HEIGHT - MARGIN.bottom + 18}
              textAnchor="middle"
              fontSize="10"
              fill={COLOR_TEXT}
            >
              {new Date(t).getUTCFullYear()}
            </text>
          </g>
        ))}

        {/* Ε.Α. segments — μία polyline ανά συνεχόμενη ομάδα, σπάει στα Σ.Α. */}
        {segments.map((seg, i) => (
          <polyline
            key={i}
            data-testid="ea-segment"
            points={seg.map((p) => `${p.x.toFixed(1)},${(p.y as number).toFixed(1)}`).join(' ')}
            fill="none"
            stroke={COLOR_EA}
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
        ))}

        {/* Σ.Α. labeled gaps */}
        {placed
          .filter((p) => p.y === null)
          .map((p) => (
            <g
              key={p.index}
              data-testid="sa-gap"
              onMouseEnter={() => setActive(p.index)}
              onClick={() => setActive(p.index)}
              style={{ cursor: 'pointer' }}
            >
              <title>{`${p.point.kind} ${p.point.period} — χωρίς βαθμολογία · ${p.point.doc_id} · σελ. ${p.point.page ?? '—'}`}</title>
              <line
                x1={p.x}
                x2={p.x}
                y1={MARGIN.top}
                y2={HEIGHT - MARGIN.bottom}
                stroke={active === p.index ? COLOR_ACTIVE : COLOR_SA}
                strokeWidth="1.5"
                strokeDasharray="3 3"
              />
              <rect x={p.x - 9} y={MARGIN.top - 26} width="18" height="14" rx="3" fill="#131318" stroke={COLOR_SA} />
              <text x={p.x} y={MARGIN.top - 16} textAnchor="middle" fontSize="9" fill={COLOR_TEXT_STRONG}>
                Σ.Α.
              </text>
              {/* ευρύτερη αόρατη ζώνη για hover */}
              <rect x={p.x - 6} y={MARGIN.top} width="12" height={plotH} fill="transparent" />
            </g>
          ))}

        {/* Ε.Α. points */}
        {placed
          .filter((p) => p.y !== null)
          .map((p) => (
            <g
              key={p.index}
              data-testid="ea-point"
              onMouseEnter={() => setActive(p.index)}
              onClick={() => setActive(p.index)}
              style={{ cursor: 'pointer' }}
            >
              <title>{`${p.point.kind} ${p.point.period} — ${p.point.score} · ${p.point.doc_id} · σελ. ${p.point.page ?? '—'}`}</title>
              <circle cx={p.x} cy={p.y as number} r="9" fill="transparent" />
              <circle
                cx={p.x}
                cy={p.y as number}
                r={active === p.index ? 5 : 3.5}
                fill={active === p.index ? COLOR_ACTIVE : COLOR_EA}
                stroke="#0a0a0c"
                strokeWidth="1"
              />
            </g>
          ))}
      </svg>

      <div
        data-testid="timeline-details"
        className="rounded-lg border px-3 py-2.5 font-mono text-[12px]"
        style={{ borderColor: '#26262d', backgroundColor: '#131318', color: COLOR_TEXT, minHeight: 44 }}
      >
        {activePoint === null ? (
          <span>Περάστε τον δείκτη ή κάντε κλικ σε ένα σημείο για doc_id και σελίδα.</span>
        ) : (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span style={{ color: COLOR_TEXT_STRONG }} className="font-semibold">
              {activePoint.point.kind}
            </span>
            <span>{activePoint.point.period}</span>
            <span style={{ color: COLOR_TEXT_STRONG }}>
              {activePoint.point.score === null ? 'χωρίς βαθμολογία' : `βαθμός ${activePoint.point.score}`}
            </span>
            <span aria-hidden>·</span>
            <span className="font-semibold">{activePoint.point.doc_id}</span>
            <span aria-hidden>·</span>
            <span>σελίδα {activePoint.point.page ?? '—'}</span>
            <span aria-hidden>·</span>
            <span>{activePoint.point.section}</span>
          </div>
        )}
      </div>
    </div>
  )
}
