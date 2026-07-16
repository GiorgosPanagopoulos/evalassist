import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryForm, type QueryFormApi } from './QueryForm'
import type { SemanticResult, StructuredResult } from '../api/types'

const PERSONS = [
  { person_id: 'p1', name: 'Άννα' },
  { person_id: 'p2', name: 'Γιώργος' },
]

const PERIODS: Record<string, string[]> = {
  p1: ['2024-Q1', '2024-Q2'],
  p2: ['2023-Q4'],
}

const structuredResult: StructuredResult = {
  mode: 'structured',
  data: {},
  sources: [],
  retrieved_doc_ids: [],
}

const semanticResult: SemanticResult = {
  mode: 'semantic',
  answer: 'ok',
  citations: [],
  retrieved_doc_ids: [],
  model: 'qwen2.5:14b',
  routing_hint: null,
}

function makeFakeApi(overrides: Partial<QueryFormApi> = {}): QueryFormApi {
  return {
    getPersons: vi.fn(async () => PERSONS),
    getPeriods: vi.fn(async (personId: string) => PERIODS[personId] ?? []),
    queryStructured: vi.fn(async () => ({ result: structuredResult, audit_id: 1 })),
    querySemantic: vi.fn(async () => ({ result: semanticResult, audit_id: 2 })),
    ...overrides,
  }
}

describe('QueryForm', () => {
  it('loads persons into the select', async () => {
    const api = makeFakeApi()
    render(<QueryForm api={api} onResult={vi.fn()} />)

    expect(await screen.findByRole('option', { name: 'Άννα (p1)' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Γιώργος (p2)' })).toBeInTheDocument()
  })

  it('shows bare (ΑΓΜ) for a person without a name', async () => {
    const api = makeFakeApi({
      getPersons: vi.fn(async () => [...PERSONS, { person_id: 'p3', name: '' }]),
    })
    render(<QueryForm api={api} onResult={vi.fn()} />)

    expect(await screen.findByRole('option', { name: '(p3)' })).toBeInTheDocument()
  })

  it('fetches and shows periods when a person is chosen', async () => {
    const api = makeFakeApi()
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={vi.fn()} />)

    await screen.findByRole('option', { name: 'Άννα (p1)' })
    await user.selectOptions(screen.getByLabelText('Άτομο'), 'p1')

    expect(api.getPeriods).toHaveBeenCalledWith('p1')
    expect(await screen.findByRole('option', { name: '2024-Q1' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '2024-Q2' })).toBeInTheDocument()
  })

  it('switches fields when the mode toggle changes', async () => {
    const api = makeFakeApi()
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={vi.fn()} />)

    expect(screen.getByLabelText('Λειτουργία')).toBeInTheDocument()
    expect(screen.queryByLabelText('Ερώτηση')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Σημασιολογική' }))

    expect(screen.getByLabelText('Ερώτηση')).toBeInTheDocument()
    expect(screen.queryByLabelText('Λειτουργία')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Δομημένη' }))
    expect(screen.getByLabelText('Λειτουργία')).toBeInTheDocument()
  })

  it('shows the other_period field for compare_periods', async () => {
    const api = makeFakeApi()
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={vi.fn()} />)

    expect(screen.queryByLabelText('Περίοδος σύγκρισης')).not.toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Λειτουργία'), 'compare_periods')

    expect(screen.getByLabelText('Περίοδος σύγκρισης')).toBeInTheDocument()
  })

  it('blocks submit when the semantic question is under 3 characters', async () => {
    const api = makeFakeApi()
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={vi.fn()} />)

    await screen.findByRole('option', { name: 'Άννα (p1)' })
    await user.selectOptions(screen.getByLabelText('Άτομο'), 'p1')
    await screen.findByRole('option', { name: '2024-Q1' })
    await user.selectOptions(screen.getByLabelText('Περίοδος'), '2024-Q1')
    await user.click(screen.getByRole('button', { name: 'Σημασιολογική' }))

    await user.type(screen.getByLabelText('Ερώτηση'), 'ab')

    expect(screen.getByRole('button', { name: /Υποβολή ερωτήματος/ })).toBeDisabled()

    await user.type(screen.getByLabelText('Ερώτηση'), 'c')
    expect(screen.getByRole('button', { name: /Υποβολή ερωτήματος/ })).toBeEnabled()
  })

  it('submits the exact structured payload', async () => {
    const api = makeFakeApi()
    const onResult = vi.fn()
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={onResult} />)

    await screen.findByRole('option', { name: 'Άννα (p1)' })
    await user.selectOptions(screen.getByLabelText('Άτομο'), 'p1')
    await screen.findByRole('option', { name: '2024-Q1' })
    await user.selectOptions(screen.getByLabelText('Περίοδος'), '2024-Q1')

    await user.click(screen.getByRole('button', { name: /Υποβολή ερωτήματος/ }))

    await waitFor(() =>
      expect(api.queryStructured).toHaveBeenCalledWith({
        person_id: 'p1',
        period: '2024-Q1',
        operation: 'get_scores',
      }),
    )
    expect(onResult).toHaveBeenCalledWith(structuredResult, 1)
  })

  it('submits the exact semantic payload', async () => {
    const api = makeFakeApi()
    const onResult = vi.fn()
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={onResult} />)

    await screen.findByRole('option', { name: 'Άννα (p1)' })
    await user.selectOptions(screen.getByLabelText('Άτομο'), 'p1')
    await screen.findByRole('option', { name: '2024-Q1' })
    await user.selectOptions(screen.getByLabelText('Περίοδος'), '2024-Q1')
    await user.click(screen.getByRole('button', { name: 'Σημασιολογική' }))
    await user.type(screen.getByLabelText('Ερώτηση'), 'Πώς πήγε;')

    await user.click(screen.getByRole('button', { name: /Υποβολή ερωτήματος/ }))

    await waitFor(() =>
      expect(api.querySemantic).toHaveBeenCalledWith({
        person_id: 'p1',
        period: '2024-Q1',
        question: 'Πώς πήγε;',
      }),
    )
    expect(onResult).toHaveBeenCalledWith(semanticResult, 2)
  })
})
