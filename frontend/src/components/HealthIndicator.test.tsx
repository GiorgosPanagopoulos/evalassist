import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { HealthIndicator, type HealthIndicatorApi } from './HealthIndicator'

describe('HealthIndicator', () => {
  it('shows the ok state when Ollama is reachable', async () => {
    const api: HealthIndicatorApi = {
      getHealth: vi.fn(async () => ({ status: 'ok', ollama_reachable: true })),
    }

    render(<HealthIndicator api={api} />)

    expect(await screen.findByText('Ollama διαθέσιμο')).toBeInTheDocument()
  })

  it('shows the unreachable warning state when Ollama is down', async () => {
    const api: HealthIndicatorApi = {
      getHealth: vi.fn(async () => ({ status: 'ok', ollama_reachable: false })),
    }

    render(<HealthIndicator api={api} />)

    expect(await screen.findByText('Ollama μη διαθέσιμο')).toBeInTheDocument()
  })
})
