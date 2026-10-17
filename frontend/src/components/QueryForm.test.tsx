import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  CAREER_PERIOD,
  CAREER_WIDE_TEXT,
  QueryForm,
  SEMANTIC_DISABLED_TEXT,
  type QueryFormApi,
} from './QueryForm'
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
  citations: [],
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

async function pickPerson(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(screen.getByRole('combobox', { name: 'Άτομο' }))
  await user.click(await screen.findByRole('option', { name }))
}

describe('QueryForm', () => {
  it('loads persons into the person search', async () => {
    const api = makeFakeApi()
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={vi.fn()} />)

    await user.click(screen.getByRole('combobox', { name: 'Άτομο' }))
    expect(await screen.findByRole('option', { name: 'Άννα (p1)' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Γιώργος (p2)' })).toBeInTheDocument()
  })

  it('shows bare (ΑΓΜ) for a person without a name', async () => {
    const api = makeFakeApi({
      getPersons: vi.fn(async () => [...PERSONS, { person_id: 'p3', name: '' }]),
    })
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={vi.fn()} />)

    await user.click(screen.getByRole('combobox', { name: 'Άτομο' }))
    expect(await screen.findByRole('option', { name: '(p3)' })).toBeInTheDocument()
  })

  it('filters the person search by Α.Γ.Μ. (Latin M too) or name without accents, and Enter picks without submitting', async () => {
    const api = makeFakeApi({
      getPersons: vi.fn(async () => [
        { person_id: 'Μ-00001', name: 'Άννα' },
        { person_id: 'Μ-00002', name: 'Γιώργος' },
      ]),
    })
    const onPersonChange = vi.fn()
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={vi.fn()} onPersonChange={onPersonChange} />)

    const combobox = screen.getByRole('combobox', { name: 'Άτομο' })
    expect(combobox).toHaveAttribute('placeholder', 'Όνομα ή Α.Γ.Μ.')
    await user.click(combobox)
    await user.type(combobox, 'm-00002')
    const listbox = screen.getByRole('listbox', { name: 'Άτομα' })
    expect(within(listbox).getAllByRole('option').map((o) => o.getAttribute('aria-label'))).toEqual([
      'Γιώργος (Μ-00002)',
    ])

    await user.clear(combobox)
    await user.type(combobox, 'αννα')
    expect(within(listbox).getAllByRole('option').map((o) => o.getAttribute('aria-label'))).toEqual(['Άννα (Μ-00001)'])

    await user.keyboard('{Enter}')
    expect(onPersonChange).toHaveBeenCalledWith({ person_id: 'Μ-00001', name: 'Άννα' })
    expect(api.queryStructured).not.toHaveBeenCalled()
    expect(combobox).toHaveValue('Άννα')
  })

  it('Ctrl+K focuses the person search', async () => {
    const user = userEvent.setup()
    render(<QueryForm api={makeFakeApi()} onResult={vi.fn()} />)

    await user.keyboard('{Control>}k{/Control}')
    expect(screen.getByRole('combobox', { name: 'Άτομο' })).toHaveFocus()
    expect(screen.getByRole('combobox', { name: 'Άτομο' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('the timeline operation needs no period and asks the parent to reload the timeline', async () => {
    const api = makeFakeApi()
    const onTimelineRequest = vi.fn()
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={vi.fn()} onTimelineRequest={onTimelineRequest} />)

    await pickPerson(user, 'Άννα (p1)')
    await user.selectOptions(screen.getByLabelText('Λειτουργία'), 'timeline')
    expect(screen.queryByLabelText('Περίοδος')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Υποβολή ερωτήματος/ }))
    expect(onTimelineRequest).toHaveBeenCalledTimes(1)
    expect(api.queryStructured).not.toHaveBeenCalled()
  })

  it('fetches and shows periods when a person is chosen', async () => {
    const api = makeFakeApi()
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={vi.fn()} />)

    await pickPerson(user, 'Άννα (p1)')

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

  it('disables the Σημασιολογική option with an explanation when semanticEnabled=false', async () => {
    const api = makeFakeApi()
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={vi.fn()} semanticEnabled={false} />)

    const semantic = screen.getByRole('button', { name: 'Σημασιολογική' })
    expect(semantic).toBeDisabled()
    expect(semantic).toHaveAttribute('title', SEMANTIC_DISABLED_TEXT)
    expect(screen.getByText(SEMANTIC_DISABLED_TEXT)).toBeInTheDocument()

    await user.click(semantic)
    expect(screen.queryByLabelText('Ερώτηση')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Λειτουργία')).toBeInTheDocument()
    expect(api.querySemantic).not.toHaveBeenCalled()
  })

  it('enables the Σημασιολογική option by default, without the explanation', () => {
    render(<QueryForm api={makeFakeApi()} onResult={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Σημασιολογική' })).toBeEnabled()
    expect(screen.queryByText(SEMANTIC_DISABLED_TEXT)).not.toBeInTheDocument()
  })

  it('replaces the single period field with an Από/Έως pair for compare_periods', async () => {
    const api = makeFakeApi()
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={vi.fn()} />)

    expect(screen.getByLabelText('Περίοδος')).toBeInTheDocument()
    expect(screen.queryByLabelText('Έως')).not.toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Λειτουργία'), 'compare_periods')

    expect(screen.queryByLabelText('Περίοδος')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Από')).toBeInTheDocument()
    expect(screen.getByLabelText('Έως')).toBeInTheDocument()
  })

  it('submits the compare_periods payload using the Από/Έως fields', async () => {
    const api = makeFakeApi()
    const onResult = vi.fn()
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={onResult} />)

    await pickPerson(user, 'Άννα (p1)')
    await screen.findByRole('option', { name: '2024-Q1' })
    await user.selectOptions(screen.getByLabelText('Λειτουργία'), 'compare_periods')
    await user.selectOptions(screen.getByLabelText('Από'), '2024-Q1')
    await user.selectOptions(screen.getByLabelText('Έως'), '2024-Q2')

    await user.click(screen.getByRole('button', { name: /Υποβολή ερωτήματος/ }))

    await waitFor(() =>
      expect(api.queryStructured).toHaveBeenCalledWith({
        person_id: 'p1',
        period: '2024-Q1',
        operation: 'compare_periods',
        other_period: '2024-Q2',
      }),
    )
    expect(onResult).toHaveBeenCalledWith(structuredResult, 1, 'p1')
  })

  it('blocks submit when the semantic question is under 3 characters', async () => {
    const api = makeFakeApi()
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={vi.fn()} />)

    await pickPerson(user, 'Άννα (p1)')
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

    await pickPerson(user, 'Άννα (p1)')
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
    expect(onResult).toHaveBeenCalledWith(structuredResult, 1, 'p1')
  })

  it('submits the exact semantic payload', async () => {
    const api = makeFakeApi()
    const onResult = vi.fn()
    const user = userEvent.setup()
    render(<QueryForm api={api} onResult={onResult} />)

    await pickPerson(user, 'Άννα (p1)')
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
    expect(onResult).toHaveBeenCalledWith(semanticResult, 2, 'p1')
  })

  describe('career-wide operations', () => {
    const CAREER_OPERATIONS = [
      { value: 'get_promotions_table', label: 'Κρίσεις προαγωγών' },
      { value: 'get_service_time_table', label: 'Συνολικός χρόνος υπηρεσίας' },
    ] as const

    it('offers both career-wide operations', () => {
      render(<QueryForm api={makeFakeApi()} onResult={vi.fn()} />)

      for (const op of CAREER_OPERATIONS) {
        const option = screen.getByRole('option', { name: op.label }) as HTMLOptionElement
        expect(option.value).toBe(op.value)
      }
    })

    for (const op of CAREER_OPERATIONS) {
      it(`hides the period field and shows the career-wide text for ${op.value}`, async () => {
        const user = userEvent.setup()
        render(<QueryForm api={makeFakeApi()} onResult={vi.fn()} />)

        expect(screen.getByLabelText('Περίοδος')).toBeInTheDocument()
        await user.selectOptions(screen.getByLabelText('Λειτουργία'), op.value)

        expect(screen.queryByLabelText('Περίοδος')).not.toBeInTheDocument()
        expect(screen.queryByLabelText('Από')).not.toBeInTheDocument()
        expect(screen.queryByRole('option', { name: 'Επιλέξτε περίοδο' })).not.toBeInTheDocument()
        expect(screen.getByTestId('career-wide-note')).toHaveTextContent(CAREER_WIDE_TEXT)
        expect(screen.getByText('Αφορά όλη τη σταδιοδρομία')).toBeInTheDocument()
      })

      it(`submits the ${op.value} payload with only the person chosen`, async () => {
        const api = makeFakeApi()
        const onResult = vi.fn()
        const user = userEvent.setup()
        render(<QueryForm api={api} onResult={onResult} />)

        await pickPerson(user, 'Άννα (p1)')
        await user.selectOptions(screen.getByLabelText('Λειτουργία'), op.value)
        await user.click(screen.getByRole('button', { name: /Υποβολή ερωτήματος/ }))

        await waitFor(() => expect(api.queryStructured).toHaveBeenCalledTimes(1))
        expect(api.queryStructured).toHaveBeenCalledWith({
          person_id: 'p1',
          period: CAREER_PERIOD,
          operation: op.value,
        })
        expect(CAREER_PERIOD).toBe('career')
        expect(onResult).toHaveBeenCalledWith(structuredResult, 1, 'p1')
      })
    }

    it('shows the period field again when switching back to get_scores', async () => {
      const api = makeFakeApi()
      const user = userEvent.setup()
      render(<QueryForm api={api} onResult={vi.fn()} />)

      await pickPerson(user, 'Άννα (p1)')
      await screen.findByRole('option', { name: '2024-Q1' })
      await user.selectOptions(screen.getByLabelText('Λειτουργία'), 'get_promotions_table')
      expect(screen.queryByLabelText('Περίοδος')).not.toBeInTheDocument()

      await user.selectOptions(screen.getByLabelText('Λειτουργία'), 'get_scores')

      expect(screen.getByLabelText('Περίοδος')).toBeInTheDocument()
      expect(screen.queryByTestId('career-wide-note')).not.toBeInTheDocument()
      // get_scores χρειάζεται ξανά περίοδο για submit
      expect(screen.getByRole('button', { name: /Υποβολή ερωτήματος/ })).toBeDisabled()
      await user.selectOptions(screen.getByLabelText('Περίοδος'), '2024-Q1')
      await user.click(screen.getByRole('button', { name: /Υποβολή ερωτήματος/ }))
      await waitFor(() =>
        expect(api.queryStructured).toHaveBeenCalledWith({
          person_id: 'p1',
          period: '2024-Q1',
          operation: 'get_scores',
        }),
      )
    })
  })
})
