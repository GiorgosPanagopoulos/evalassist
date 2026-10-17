import { describe, expect, it, vi } from 'vitest'
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

  it('never draws a line through a Σ.Α. gap: the Ε.Α. polyline is split around it', () => {
    render(<TimelineChart points={POINTS} />)

    const segments = screen.getAllByTestId('ea-segment')
    expect(segments).toHaveLength(2)
    const coords = (el: Element) => (el.getAttribute('points') ?? '').split(' ')
    expect(coords(segments[0])).toHaveLength(2)
    expect(coords(segments[1])).toHaveLength(2)
    // Κανένα segment δεν μπαίνει στη ζώνη του κενού.
    const band = screen.getByTestId('sa-gap').querySelector('rect')!
    const bandStart = Number(band.getAttribute('x'))
    const bandEnd = bandStart + Number(band.getAttribute('width'))
    const seg0MaxX = Math.max(...coords(segments[0]).map((c) => Number(c.split(',')[0])))
    const seg1MinX = Math.min(...coords(segments[1]).map((c) => Number(c.split(',')[0])))
    expect(seg0MaxX).toBeLessThan(bandStart)
    expect(seg1MinX).toBeGreaterThan(bandEnd)
  })

  it('does not fill the Σ.Α. from neighbours: the gap has no y coordinate/score', () => {
    render(<TimelineChart points={POINTS} />)

    const gap = screen.getByTestId('sa-gap')
    expect(gap.querySelector('circle')).toBeNull()
    expect(gap.querySelector('title')?.textContent).toContain('χωρίς βαθμολογία')
    expect(gap.querySelector('title')?.textContent).not.toMatch(/\b(100|98|95|97\.5)\b/)
  })

  it('defaults to a fixed 80-100 axis marked as broken, with 0-100 and zoom toggles', () => {
    render(<TimelineChart points={POINTS} />)

    const fixed = screen.getByRole('button', { name: '80-100' })
    expect(fixed).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('img', { name: /άξονας Y 80-100/ })).toBeInTheDocument()
    expect(screen.getByTestId('axis-break')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '0-100' }))
    expect(screen.getByRole('img', { name: /άξονας Y 0-100/ })).toBeInTheDocument()
    expect(screen.queryByTestId('axis-break')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Μεγέθυνση' }))
    expect(screen.getByRole('img', { name: /άξονας Y 94-100/ })).toBeInTheDocument()
  })

  it('never clips a score below 80: the fixed axis extends and says so', () => {
    render(<TimelineChart points={[ea('2005-01-01..2005-12-31', 72, 1), ea('2006-01-01..2006-12-31', 90, 1)]} />)
    expect(screen.getByRole('img', { name: /άξονας Y 72-100/ })).toBeInTheDocument()
    expect(screen.getByTestId('scale-extended')).toHaveTextContent('Κλίμακα επεκτάθηκε σε 72-100')

    fireEvent.click(screen.getByRole('button', { name: '0-100' }))
    expect(screen.queryByTestId('scale-extended')).not.toBeInTheDocument()
  })

  it('puts the "ελάχ." label beside the minimum when it sits on the x axis', () => {
    render(<TimelineChart points={[ea('2005-01-01..2005-12-31', 72, 1), ea('2006-01-01..2006-12-31', 90, 1)]} />)
    const label = screen.getByTestId('min-marker')
    const point = screen.getAllByTestId('ea-point')[0].querySelectorAll('circle')[1]
    expect(label).toHaveAttribute('text-anchor', 'start')
    expect(Number(label.getAttribute('x'))).toBeGreaterThan(Number(point.getAttribute('cx')))
    expect(Number(label.getAttribute('y'))).toBeLessThan(Number(point.getAttribute('cy')))
  })

  it('no extension note while every score fits 80-100', () => {
    render(<TimelineChart points={POINTS} />)
    expect(screen.queryByTestId('scale-extended')).not.toBeInTheDocument()
  })

  it('labels each Σ.Α. band', () => {
    render(<TimelineChart points={POINTS} />)
    const label = screen.getByTestId('sa-gap').querySelector('text')
    expect(label).toHaveTextContent('Σ.Α.')
    expect(label).toHaveAttribute('font-size', '10')
  })

  it('the tooltip never covers its point, the other points or the "ελάχ." label', () => {
    render(<TimelineChart points={POINTS} />)

    const boxes = screen.getAllByTestId('ea-point').map((g) => {
      const c = g.querySelectorAll('circle')[1]
      return { x: Number(c.getAttribute('cx')) - 6, y: Number(c.getAttribute('cy')) - 6, w: 12, h: 12 }
    })
    const label = screen.getByTestId('min-marker')
    boxes.push({ x: Number(label.getAttribute('x')) - 30, y: Number(label.getAttribute('y')) - 10, w: 60, h: 12 })

    for (const point of screen.getAllByTestId('ea-point')) {
      fireEvent.mouseEnter(point)
      const tip = screen.getByTestId('timeline-tooltip')
      const t = {
        x: parseFloat(tip.style.left),
        y: parseFloat(tip.style.top),
        w: parseFloat(tip.style.width),
        h: parseFloat(tip.style.minHeight),
      }
      for (const b of boxes) {
        const hit = t.x < b.x + b.w && b.x < t.x + t.w && t.y < b.y + b.h && b.y < t.y + t.h
        expect(hit).toBe(false)
      }
    }
  })

  it('keeps the tooltip inside the chart at the left and right edges', () => {
    render(<TimelineChart points={POINTS} />)

    for (const point of [screen.getAllByTestId('ea-point')[0], screen.getAllByTestId('ea-point')[3]]) {
      fireEvent.mouseEnter(point)
      const tip = screen.getByTestId('timeline-tooltip')
      const left = parseFloat(tip.style.left)
      expect(left).toBeGreaterThanOrEqual(0)
      expect(left + parseFloat(tip.style.width)).toBeLessThanOrEqual(960)
    }
  })

  it('draws a dashed mean line and marks the minimum', () => {
    render(<TimelineChart points={POINTS} />)

    expect(screen.getByTestId('mean-line')).toHaveAttribute('stroke-dasharray')
    expect(screen.getByTestId('min-marker')).toHaveTextContent('ελάχ. 95')
    expect(screen.getByText('Μέσος 98,3')).toBeInTheDocument()
  })

  it('hover shows period, score, delta from previous, doc_id, page and section', () => {
    render(<TimelineChart points={POINTS} />)

    fireEvent.mouseEnter(screen.getAllByTestId('ea-point')[2])
    const tip = screen.getByTestId('timeline-tooltip')
    expect(tip).toHaveTextContent('Ε.Α.')
    expect(tip).toHaveTextContent('95')
    // The previous scored period is 100: the Σ.Α. in between is skipped.
    expect(tip).toHaveTextContent('Δ -5')
    expect(tip).toHaveTextContent('doc-1 · σελ. 7')
    expect(tip).toHaveTextContent(SECTION)

    fireEvent.mouseEnter(screen.getByTestId('sa-gap'))
    const gapTip = screen.getByTestId('timeline-tooltip')
    expect(gapTip).toHaveTextContent('Σ.Α.')
    expect(gapTip).toHaveTextContent('χωρίς βαθμό')
    expect(gapTip).toHaveTextContent('σελ. 8')
    expect(gapTip.textContent).not.toMatch(/Δ /)
  })

  it('clicking a point or a gap selects that period', () => {
    const onSelect = vi.fn()
    render(<TimelineChart points={POINTS} selected={3} onSelect={onSelect} />)

    expect(screen.getAllByTestId('ea-point')[2]).toHaveAttribute('data-selected', 'true')
    fireEvent.click(screen.getAllByTestId('ea-point')[0])
    expect(onSelect).toHaveBeenLastCalledWith(0)
    fireEvent.click(screen.getByTestId('sa-gap'))
    expect(onSelect).toHaveBeenLastCalledWith(2)
  })

  it('renders an empty message when there are no points', () => {
    render(<TimelineChart points={[]} />)
    expect(screen.getByText(/Καμία αξιολόγηση/)).toBeInTheDocument()
  })
})
