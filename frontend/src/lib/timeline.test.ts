import { describe, expect, it } from 'vitest'
import type { TimelinePoint } from '../api/types'
import { periodParts, scaleDomain } from './timeline'

function point(period: string, score: number | null = 95): TimelinePoint {
  return { period, period_start: period.slice(0, 10), kind: 'Ε.Α.', score, doc_id: 'd', page: 1, section: 's' }
}

describe('periodParts', () => {
  it('names exact half-years and years without a range', () => {
    expect(periodParts(point('2012-01-01..2012-06-30'))).toEqual({ title: '2012 Αʹ', range: null })
    expect(periodParts(point('2012-07-01..2012-12-31'))).toEqual({ title: '2012 Βʹ', range: null })
    expect(periodParts(point('2012-01-01..2012-12-31'))).toEqual({ title: '2012', range: null })
  })

  it('gives the year and the day/month range otherwise', () => {
    expect(periodParts(point('2024-01-01..2024-07-02'))).toEqual({ title: '2024', range: ['01/01', '02/07'] })
    expect(periodParts(point('2005-07-05..2006-03-31'))).toEqual({
      title: '2005-2006',
      range: ['05/07/2005', '31/03/2006'],
    })
  })
})

describe('scaleDomain', () => {
  const points = [point('2020-01-01..2020-12-31', 93), point('2021-01-01..2021-12-31', null)]

  it('is 80-100 fixed, 0-100 full, and one below the minimum on zoom', () => {
    expect(scaleDomain('fixed', points)).toEqual([80, 100])
    expect(scaleDomain('full', points)).toEqual([0, 100])
    expect(scaleDomain('zoom', points)).toEqual([92, 100])
  })

  it('extends the fixed axis below 80 instead of clipping', () => {
    expect(scaleDomain('fixed', [point('2020-01-01..2020-12-31', 71.5)])).toEqual([71, 100])
  })
})
