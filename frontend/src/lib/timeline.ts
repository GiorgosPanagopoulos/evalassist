import type { TimelinePoint } from '../api/types'

const DAY_MS = 24 * 60 * 60 * 1000

export interface PeriodRange {
  start: number
  end: number
}

// "YYYY-MM-DD..YYYY-MM-DD" in UTC. A single date is a one-day period.
export function periodRange(point: TimelinePoint): PeriodRange {
  const [startText, endText] = point.period.split('..')
  const start = Date.parse(startText ?? point.period_start)
  const end = Date.parse(endText ?? '')
  return { start, end: Number.isNaN(end) ? start + DAY_MS : end + DAY_MS }
}

export function periodMid(point: TimelinePoint): number {
  const { start, end } = periodRange(point)
  return (start + end) / 2
}

function dm(text: string): string {
  const [, m, d] = text.split('-')
  return `${d}/${m}`
}

function dmy(text: string): string {
  return `${dm(text)}/${text.slice(0, 4)}`
}

export interface PeriodParts {
  title: string
  // Date range, only when the period is not an exact half-year or year.
  range: [string, string] | null
}

// "2012 Αʹ" / "2012 Βʹ" only for exact half-years, the year for exact years,
// otherwise the year plus the date range, so two rows never share a label.
export function periodParts(point: TimelinePoint): PeriodParts {
  const [start, end] = point.period.split('..')
  if (!start || !end) return { title: point.period, range: null }
  const year = start.slice(0, 4)
  const endYear = end.slice(0, 4)
  if (endYear === year) {
    const span = `${start.slice(5)}..${end.slice(5)}`
    if (span === '01-01..06-30') return { title: `${year} Αʹ`, range: null }
    if (span === '07-01..12-31') return { title: `${year} Βʹ`, range: null }
    if (span === '01-01..12-31') return { title: year, range: null }
    return { title: year, range: [dm(start), dm(end)] }
  }
  return { title: `${year}-${endYear}`, range: [dmy(start), dmy(end)] }
}

export function periodLabel(point: TimelinePoint): string {
  const { title, range } = periodParts(point)
  return range ? `${title} ${range[0]} - ${range[1]}` : title
}

export type ScaleMode = 'fixed' | 'full' | 'zoom'

export const FIXED_FLOOR = 80

// Shared by the chart axis and the list bars. Never clips a value: below 80
// the fixed axis extends down.
export function scaleDomain(scale: ScaleMode, points: TimelinePoint[]): [number, number] {
  const scores = points.map((p) => p.score).filter((s): s is number => s !== null)
  const lowest = scores.length ? Math.min(...scores) : 100
  if (scale === 'full') return [0, 100]
  if (scale === 'fixed') return [Math.min(FIXED_FLOOR, Math.floor(lowest)), 100]
  return [Math.max(0, Math.min(99, Math.floor(lowest) - 1)), 100]
}

const NUMBER = new Intl.NumberFormat('el-GR', { maximumFractionDigits: 1 })

export function formatScore(value: number): string {
  return NUMBER.format(value)
}

export function formatDelta(value: number): string {
  if (value === 0) return '±0'
  return value > 0 ? `+${formatScore(value)}` : `-${formatScore(-value)}`
}

export interface TimelineStats {
  periods: number
  mean: number | null
  min: number | null
  last: number | null
}

export function timelineStats(points: TimelinePoint[]): TimelineStats {
  const scores = points.map((p) => p.score).filter((s): s is number => s !== null)
  if (scores.length === 0) return { periods: points.length, mean: null, min: null, last: null }
  return {
    periods: points.length,
    mean: scores.reduce((a, b) => a + b, 0) / scores.length,
    min: Math.min(...scores),
    last: scores[scores.length - 1],
  }
}

// Difference from the previous scored period; Σ.Α. in between are skipped,
// never interpolated.
export function deltaFromPrevious(points: TimelinePoint[], index: number): number | null {
  const score = points[index]?.score
  if (score === null || score === undefined) return null
  for (let i = index - 1; i >= 0; i -= 1) {
    const prev = points[i].score
    if (prev !== null) return score - prev
  }
  return null
}

export function pageText(page: number | null): string {
  return page === null ? 'σελίδα δεν καταγράφηκε' : `σελ. ${page}`
}

export function citationText(point: TimelinePoint): string {
  return `${point.doc_id} · ${pageText(point.page)} · ${point.section}`
}

function csvCell(value: string | number | null): string {
  const text = value === null ? '' : String(value)
  return /[;"\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

// ";" and a BOM so that Excel with Greek locale opens it as columns, in UTF-8.
export function timelineCsv(personId: string, points: TimelinePoint[]): string {
  const header = ['person_id', 'period', 'kind', 'score', 'doc_id', 'page', 'section']
  const rows = points.map((p) => [personId, p.period, p.kind, p.score, p.doc_id, p.page, p.section])
  return '﻿' + [header, ...rows].map((row) => row.map(csvCell).join(';')).join('\r\n') + '\r\n'
}
