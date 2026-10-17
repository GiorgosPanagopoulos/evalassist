import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import type { TimelinePoint } from '../api/types'
import { LOADING_TEXT, REVOKE_AFTER_MS, openDocument } from './openDocument'

const POINT: TimelinePoint = {
  period: '2012-09-14..2012-12-31',
  period_start: '2012-09-14',
  kind: 'Ε.Α.',
  score: 93,
  doc_id: '29b215931c674b6e',
  page: 7,
  section: 'ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ',
}

function fakeTab() {
  return {
    opener: {} as unknown,
    document: { title: '', body: { textContent: '' } },
    location: { href: '' },
    close: vi.fn(),
  }
}

function fakeWindow(tab: ReturnType<typeof fakeTab> | null) {
  return { open: vi.fn(() => tab as unknown as Window) }
}

const pdf = () => new Blob(['%PDF-1.4'], { type: 'application/pdf' })

describe('openDocument', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    URL.createObjectURL = vi.fn(() => 'blob:http://10.0.0.5/abc')
    URL.revokeObjectURL = vi.fn()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('opens the tab before the request, then shows the blob at the page', async () => {
    const tab = fakeTab()
    const win = fakeWindow(tab)
    const order: string[] = []
    win.open.mockImplementation(() => {
      order.push('open')
      return tab as unknown as Window
    })
    const api = {
      documentFile: vi.fn(async () => {
        order.push('request')
        // Η καρτέλα δείχνει ήδη φόρτωση και δεν έχει opener.
        expect(tab.opener).toBeNull()
        expect(tab.document.body.textContent).toBe(LOADING_TEXT)
        return pdf()
      }),
    }

    const outcome = await openDocument(api, 'Μ-01253', POINT, win)

    expect(outcome).toBe('opened')
    expect(order).toEqual(['open', 'request'])
    expect(win.open).toHaveBeenCalledWith('', '_blank')
    expect(api.documentFile).toHaveBeenCalledTimes(1)
    expect(api.documentFile).toHaveBeenCalledWith('Μ-01253', POINT.doc_id, POINT.period)
    expect(tab.location.href).toBe('blob:http://10.0.0.5/abc#page=7')
    expect(tab.close).not.toHaveBeenCalled()
    const blob = vi.mocked(URL.createObjectURL).mock.calls[0][0] as Blob
    expect(blob.type).toBe('application/pdf')
  })

  it('page null opens page 1', async () => {
    const tab = fakeTab()
    await openDocument({ documentFile: vi.fn(async () => pdf()) }, 'p1', { ...POINT, page: null }, fakeWindow(tab))
    expect(tab.location.href).toBe('blob:http://10.0.0.5/abc#page=1')
  })

  it('revokes the object URL after the delay, not before', async () => {
    await openDocument({ documentFile: vi.fn(async () => pdf()) }, 'p1', POINT, fakeWindow(fakeTab()))
    vi.advanceTimersByTime(REVOKE_AFTER_MS - 1)
    expect(URL.revokeObjectURL).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:http://10.0.0.5/abc')
  })

  it.each([
    ['404', new ApiError(404, 'Δεν βρέθηκε το έγγραφο.')],
    ['500', new ApiError(500, 'Internal server error')],
    ['network error', new TypeError('Failed to fetch')],
  ])('%s: closes the tab and reports unavailable', async (_, error) => {
    const tab = fakeTab()
    const outcome = await openDocument(
      { documentFile: vi.fn(async () => Promise.reject(error)) },
      'p1',
      POINT,
      fakeWindow(tab),
    )
    expect(outcome).toBe('unavailable')
    expect(tab.close).toHaveBeenCalledTimes(1)
    expect(tab.location.href).toBe('')
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })

  it('401: closes the tab and reports unauthorized (the client sends the user to login)', async () => {
    const tab = fakeTab()
    const outcome = await openDocument(
      { documentFile: vi.fn(async () => Promise.reject(new ApiError(401, 'x'))) },
      'p1',
      POINT,
      fakeWindow(tab),
    )
    expect(outcome).toBe('unauthorized')
    expect(tab.close).toHaveBeenCalledTimes(1)
  })

  it('blocked popup: no request at all', async () => {
    const api = { documentFile: vi.fn(async () => pdf()) }
    const outcome = await openDocument(api, 'p1', POINT, fakeWindow(null))
    expect(outcome).toBe('popup_blocked')
    expect(api.documentFile).not.toHaveBeenCalled()
  })
})
