import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ResultsPanel } from './ResultsPanel'
import type { SemanticResult, StructuredResult } from '../api/types'

describe('ResultsPanel', () => {
  it('renders a semantic result with the answer, all citations, and the audit id', () => {
    const result: SemanticResult = {
      mode: 'semantic',
      answer: 'Η απόδοση βελτιώθηκε κατά τη διάρκεια της περιόδου.',
      citations: [
        { doc_id: 'doc-1', page: 3, section: 'Επισκόπηση', score: 0.91 },
        { doc_id: 'doc-2', page: 7, section: 'Στόχοι', score: 0.85 },
      ],
      retrieved_doc_ids: ['doc-1', 'doc-2'],
      model: 'qwen2.5:14b',
      routing_hint: null,
    }

    render(<ResultsPanel result={result} auditId={42} />)

    expect(screen.getByText(result.answer)).toBeInTheDocument()
    expect(screen.getByText(/doc-1/)).toBeInTheDocument()
    expect(screen.getByText(/σελίδα 3/)).toBeInTheDocument()
    expect(screen.getByText('Επισκόπηση')).toBeInTheDocument()
    expect(screen.getByText(/doc-2/)).toBeInTheDocument()
    expect(screen.getByText(/σελίδα 7/)).toBeInTheDocument()
    expect(screen.getByText('Στόχοι')).toBeInTheDocument()
    expect(screen.getByText('Καταχώρηση ελέγχου: #42')).toBeInTheDocument()
  })

  it('always renders the ReviewBanner on a semantic result', () => {
    const result: SemanticResult = {
      mode: 'semantic',
      answer: 'ok',
      citations: [{ doc_id: 'doc-1', page: 1, section: 'A', score: 0.5 }],
      retrieved_doc_ids: ['doc-1'],
      model: 'qwen2.5:14b',
      routing_hint: null,
    }

    render(<ResultsPanel result={result} auditId={1} />)

    expect(
      screen.getByText('Συμβουλευτικό περιεχόμενο - απαιτείται ανθρώπινη αξιολόγηση'),
    ).toBeInTheDocument()
  })

  it('renders the EmptyState for an empty-scope semantic result', () => {
    const result: SemanticResult = {
      mode: 'semantic',
      answer: 'Δεν βρέθηκαν δεδομένα εντός του καθορισμένου πεδίου.',
      citations: [],
      retrieved_doc_ids: [],
      model: 'qwen2.5:14b',
      routing_hint: null,
    }

    render(<ResultsPanel result={result} auditId={5} />)

    expect(screen.getByText('Δεν βρέθηκαν δεδομένα στο εύρος')).toBeInTheDocument()
    // ReviewBanner must still be present even for the empty-scope case.
    expect(
      screen.getByText('Συμβουλευτικό περιεχόμενο - απαιτείται ανθρώπινη αξιολόγηση'),
    ).toBeInTheDocument()
  })

  it('renders a structured get_scores result as a scores table', () => {
    const result: StructuredResult = {
      mode: 'structured',
      data: {
        person_id: 'p1',
        period: '2024-Q1',
        gnmatefsi: 8.5,
        overall_comment: 'Καλή απόδοση',
        sections: [
          { section: 'Επικοινωνία', score: 9, comment: 'Άριστη' },
          { section: 'Ομαδικότητα', score: 7, comment: 'Καλή' },
        ],
      },
      sources: [],
      retrieved_doc_ids: ['doc-1'],
    }

    render(<ResultsPanel result={result} auditId={10} />)

    expect(screen.getByText('Επικοινωνία')).toBeInTheDocument()
    expect(screen.getByText('9')).toBeInTheDocument()
    expect(screen.getByText('Άριστη')).toBeInTheDocument()
    expect(screen.getByText('Ομαδικότητα')).toBeInTheDocument()
    expect(screen.getByText('Καταχώρηση ελέγχου: #10')).toBeInTheDocument()
  })

  it('shows a dismissible routing hint banner when routing_hint is "structured"', async () => {
    const user = userEvent.setup()
    const result: SemanticResult = {
      mode: 'semantic',
      answer: 'ok',
      citations: [{ doc_id: 'doc-1', page: 1, section: 'A', score: 0.5 }],
      retrieved_doc_ids: ['doc-1'],
      model: 'qwen2.5:14b',
      routing_hint: 'structured',
    }

    render(<ResultsPanel result={result} auditId={1} />)

    const banner = screen.getByText('Το ερώτημα αφορά βαθμολογία - δοκιμάστε Δομημένη αναζήτηση')
    expect(banner).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Απόρριψη πρότασης' }))

    expect(
      screen.queryByText('Το ερώτημα αφορά βαθμολογία - δοκιμάστε Δομημένη αναζήτηση'),
    ).not.toBeInTheDocument()
  })

  it('does not show the routing hint banner when routing_hint is null', () => {
    const result: SemanticResult = {
      mode: 'semantic',
      answer: 'ok',
      citations: [{ doc_id: 'doc-1', page: 1, section: 'A', score: 0.5 }],
      retrieved_doc_ids: ['doc-1'],
      model: 'qwen2.5:14b',
      routing_hint: null,
    }

    render(<ResultsPanel result={result} auditId={1} />)

    expect(
      screen.queryByText('Το ερώτημα αφορά βαθμολογία - δοκιμάστε Δομημένη αναζήτηση'),
    ).not.toBeInTheDocument()
  })

  it('shows a placeholder when there is no result yet', () => {
    render(<ResultsPanel result={null} auditId={null} />)

    expect(screen.getByText('Υποβάλετε ένα ερώτημα για να δείτε αποτελέσματα')).toBeInTheDocument()
  })
})
