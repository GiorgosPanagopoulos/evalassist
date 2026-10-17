import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TimelinePanel } from './TimelinePanel'
import type { TimelinePoint } from '../api/types'

const SECTION = 'ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ'

function ea(period: string, score: number): TimelinePoint {
  return { period, period_start: period.slice(0, 10), kind: 'Ε.Α.', score, doc_id: 'doc-1', page: 3, section: SECTION }
}

function renderPanel(points: TimelinePoint[]) {
  const api = {
    getTimeline: vi.fn(async () => ({
      result: { person_id: 'p1', points, retrieved_doc_ids: ['doc-1'] },
      audit_id: 1,
    })),
  }
  render(<TimelinePanel api={api} person={{ person_id: 'p1', name: 'Συνθετικός Α' }} />)
}

async function barWidths(): Promise<string[]> {
  const list = await screen.findByRole('list', { name: 'Λίστα περιόδων' })
  return within(list)
    .getAllByTestId('score-bar')
    .map((bar) => bar.style.width)
}

describe('TimelinePanel', () => {
  it('without a person, asks for a name or Α.Γ.Μ.', () => {
    render(<TimelinePanel api={{ getTimeline: vi.fn() }} person={null} />)
    expect(screen.getByText('Επιλέξτε άτομο από την αναζήτηση')).toBeInTheDocument()
    expect(screen.getByText('Όνομα ή Α.Γ.Μ., συντόμευση Ctrl+K')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/κωδικ/i)
  })

  it('list bars use the chart scale domain, including zoom', async () => {
    const user = userEvent.setup()
    // Newest first in the list: 90, then 100.
    renderPanel([ea('2023-01-01..2023-12-31', 100), ea('2024-01-01..2024-06-30', 90)])

    expect(await barWidths()).toEqual(['50%', '100%'])

    await user.click(screen.getByRole('button', { name: '0-100' }))
    expect(await barWidths()).toEqual(['90%', '100%'])

    // Zoom domain is 89-100.
    await user.click(screen.getByRole('button', { name: 'Μεγέθυνση' }))
    const [low, high] = await barWidths()
    expect(parseFloat(low)).toBeCloseTo((1 / 11) * 100, 5)
    expect(high).toBe('100%')
  })

  it('a non half-year period shows the year and a mono date range on two lines', async () => {
    renderPanel([ea('2007-01-26..2007-05-06', 95)])

    const list = await screen.findByRole('list', { name: 'Λίστα περιόδων' })
    const row = within(list).getByRole('button', { name: /^2007 26\/01 - 06\/05/ })
    expect(row).toHaveTextContent('2007')
    const dates = Array.from(row.querySelectorAll('.whitespace-nowrap')).map((el) => el.textContent)
    expect(dates).toEqual(['26/01', '06/05'])
  })

  it('the citation line is truncated with the full text in its title', async () => {
    renderPanel([ea('2023-01-01..2023-12-31', 100)])

    const line = await screen.findByTestId('selected-citation')
    expect(line).toHaveClass('truncate')
    expect(line).toHaveAttribute('title', `doc-1 · σελ. 3 · ${SECTION}`)
  })
})
