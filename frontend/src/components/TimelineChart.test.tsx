import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { TimelineChart } from './TimelineChart'
import type { TimelinePoint } from '../api/types'

const SECTION = 'ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ'

function ea(period: string, score: number, page: number): TimelinePoint {
  return { period, period_start: period.split('..')[0], kind: 'Ε.Α.', score, doc_id: 'doc-1', page, section: SECTION }
}

function sa(period: string, page: number): TimelinePoint {
  return { period, period_start: period.split('..')[0], kind: 'Σ.Α.', score: null, doc_id: 'doc-1', page, section: SECTION }
}

// Ε.Α. 98 → Ε.Α. 100 → Σ.Α. → Ε.Α. 95 → Ε.Α. 100 : ένα κενό στη μέση.
const POINTS: TimelinePoint[] = [
  ea('2005-07-05..2005-12-31', 98, 8),
  ea('2006-01-01..2006-12-31', 100, 8),
  sa('2007-01-01..2007-01-25', 8),
  ea('2007-01-26..2007-05-06', 95, 7),
  ea('2007-05-08..2007-12-31', 100, 7),
]

describe('TimelineChart', () => {
  it('renders one point per Ε.Α. and one labeled gap per Σ.Α.', () => {
    render(<TimelineChart points={POINTS} />)

    expect(screen.getAllByTestId('ea-point')).toHaveLength(4)
    const gaps = screen.getAllByTestId('sa-gap')
    expect(gaps).toHaveLength(1)
    expect(gaps[0].textContent).toContain('Σ.Α.')
  })

  it('never draws a line through a Σ.Α. gap — the Ε.Α. polyline is split around it', () => {
    render(<TimelineChart points={POINTS} />)

    const segments = screen.getAllByTestId('ea-segment')
    expect(segments).toHaveLength(2)
    const coords = (el: Element) => (el.getAttribute('points') ?? '').split(' ')
    expect(coords(segments[0])).toHaveLength(2)
    expect(coords(segments[1])).toHaveLength(2)
    // Κανένα segment δεν περιέχει x ανάμεσα στους δύο γείτονες του κενού.
    const gapLine = screen.getByTestId('sa-gap').querySelector('line')!
    const gapX = Number(gapLine.getAttribute('x1'))
    const seg0MaxX = Math.max(...coords(segments[0]).map((c) => Number(c.split(',')[0])))
    const seg1MinX = Math.min(...coords(segments[1]).map((c) => Number(c.split(',')[0])))
    expect(seg0MaxX).toBeLessThan(gapX)
    expect(seg1MinX).toBeGreaterThan(gapX)
  })

  it('does not fill the Σ.Α. from neighbours — the gap has no y coordinate/score', () => {
    render(<TimelineChart points={POINTS} />)

    const gap = screen.getByTestId('sa-gap')
    expect(gap.querySelector('circle')).toBeNull()
    expect(gap.querySelector('title')?.textContent).toContain('χωρίς βαθμολογία')
    expect(gap.querySelector('title')?.textContent).not.toMatch(/\b(100|98|95|97\.5)\b/)
  })

  it('marks the y axis as a truncated 93-100 range of the 0-100 scale', () => {
    render(<TimelineChart points={POINTS} />)

    expect(screen.getByText(/Περικομμένος άξονας Y/)).toBeInTheDocument()
    expect(screen.getByText(/93-100 της κλίμακας 0-100/)).toBeInTheDocument()
    expect(screen.getByTestId('axis-break')).toBeInTheDocument()
  })

  it('shows doc_id and page for a clicked point and for a clicked gap', () => {
    render(<TimelineChart points={POINTS} />)

    fireEvent.click(screen.getAllByTestId('ea-point')[3])
    let details = screen.getByTestId('timeline-details')
    expect(details.textContent).toContain('doc-1')
    expect(details.textContent).toContain('σελίδα 7')
    expect(details.textContent).toContain('βαθμός 100')

    fireEvent.click(screen.getByTestId('sa-gap'))
    details = screen.getByTestId('timeline-details')
    expect(details.textContent).toContain('Σ.Α.')
    expect(details.textContent).toContain('χωρίς βαθμολογία')
    expect(details.textContent).toContain('σελίδα 8')
  })

  it('renders an empty message when there are no points', () => {
    render(<TimelineChart points={[]} />)
    expect(screen.getByText(/Καμία αξιολόγηση/)).toBeInTheDocument()
  })
})
