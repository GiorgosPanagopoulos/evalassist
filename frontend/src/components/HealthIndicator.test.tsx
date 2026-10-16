import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ApiError } from '../api/client'
import type { HealthResponse } from '../api/types'
import { HealthIndicator, type HealthIndicatorApi } from './HealthIndicator'

const GREEN = '#3fdd78'
const AMBER = '#f59e0b'

function apiReturning(health: HealthResponse): HealthIndicatorApi {
  return { getHealth: vi.fn(async () => health) }
}

function apiRejecting(error: unknown): HealthIndicatorApi {
  return {
    getHealth: vi.fn(async () => {
      throw error
    }),
  }
}

async function expectState(text: string, dotColor: string) {
  expect(await screen.findByText(text)).toBeInTheDocument()
  expect(screen.getByTestId('health-dot')).toHaveStyle({ backgroundColor: dotColor })
  expect(screen.queryByText('Έλεγχος κατάστασης...')).not.toBeInTheDocument()
}

describe('HealthIndicator', () => {
  it('semantic closed: green "Σύστημα ενεργό", never the Ollama warning', async () => {
    render(<HealthIndicator api={apiReturning({ status: 'ok', ollama_reachable: null })} semanticEnabled={false} />)

    await expectState('Σύστημα ενεργό', GREEN)
    expect(screen.queryByText('Ollama μη διαθέσιμο')).not.toBeInTheDocument()
  })

  it('semantic closed: ignores ollama_reachable even if the server sent false', async () => {
    render(<HealthIndicator api={apiReturning({ status: 'ok', ollama_reachable: false })} semanticEnabled={false} />)

    await expectState('Σύστημα ενεργό', GREEN)
    expect(screen.queryByText('Ollama μη διαθέσιμο')).not.toBeInTheDocument()
  })

  it('semantic open + Ollama reachable: green "Σύστημα ενεργό"', async () => {
    render(<HealthIndicator api={apiReturning({ status: 'ok', ollama_reachable: true })} semanticEnabled />)

    await expectState('Σύστημα ενεργό', GREEN)
  })

  it('semantic open + Ollama unreachable: amber "Ollama μη διαθέσιμο"', async () => {
    render(<HealthIndicator api={apiReturning({ status: 'ok', ollama_reachable: false })} semanticEnabled />)

    await expectState('Ollama μη διαθέσιμο', AMBER)
  })

  it('semantic open + not checked (inconsistent server): amber "Ollama μη διαθέσιμο"', async () => {
    render(<HealthIndicator api={apiReturning({ status: 'ok', ollama_reachable: null })} semanticEnabled />)

    await expectState('Ollama μη διαθέσιμο', AMBER)
  })

  it.each([
    ['non-2xx', new ApiError(502, 'Bad Gateway')],
    ['network error', new TypeError('Failed to fetch')],
  ])('health request fails (%s): amber "Σύστημα μη διαθέσιμο", not stuck on checking', async (_label, error) => {
    for (const semanticEnabled of [false, true]) {
      const { unmount } = render(<HealthIndicator api={apiRejecting(error)} semanticEnabled={semanticEnabled} />)

      await expectState('Σύστημα μη διαθέσιμο', AMBER)
      unmount()
    }
  })
})
