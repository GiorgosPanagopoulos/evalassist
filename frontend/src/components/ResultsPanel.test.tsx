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
      citations: [],
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

  it('renders the overall field separately from the top/bottom tables', () => {
    const result: StructuredResult = {
      mode: 'structured',
      data: {
        person_id: 'p1',
        period: '2012-09-14..2012-12-31',
        top: [{ field_code: '91', description: 'ΕΠΑΓΓΕΛΜΑΤΙΚΗ ΚΑΤΑΡΤΙΣΗ', value: 94 }],
        bottom: [{ field_code: '97', description: 'ΕΠΙΤΕΛΙΚΗ ΙΚΑΝΟΤΗΤΑ', value: 90 }],
        overall: {
          field_code: '141',
          description: 'ΓΕΝΙΚΗ ΙΚΑΝΟΤΗΤΑ ΓΙΑ ΤΟΝ KATEXOMENO ΒΑΘΜΟ',
          value: 93,
        },
      },
      citations: [],
      retrieved_doc_ids: ['doc-1'],
    }

    render(<ResultsPanel result={result} auditId={11} />)

    expect(screen.getByText('Συνολική κρίση (εκτός κατάταξης)')).toBeInTheDocument()
    expect(screen.getByText('ΓΕΝΙΚΗ ΙΚΑΝΟΤΗΤΑ ΓΙΑ ΤΟΝ KATEXOMENO ΒΑΘΜΟ')).toBeInTheDocument()
    expect(screen.getByText('93')).toBeInTheDocument()
    // παραμένει έξω από τις δύο κατατάξεις
    expect(screen.getByText('Κορυφαίες ενότητες')).toBeInTheDocument()
    expect(screen.getByText('Χαμηλότερες ενότητες')).toBeInTheDocument()
  })

  it('renders nothing for the overall field when it is null', () => {
    const result: StructuredResult = {
      mode: 'structured',
      data: {
        person_id: 'p1',
        period: '2025-01-01..2025-12-31',
        top: [{ field_code: '91', description: 'ΕΠΑΓΓΕΛΜΑΤΙΚΗ ΚΑΤΑΡΤΙΣΗ', value: 94 }],
        bottom: [{ field_code: '97', description: 'ΕΠΙΤΕΛΙΚΗ ΙΚΑΝΟΤΗΤΑ', value: 90 }],
        overall: null,
      },
      citations: [],
      retrieved_doc_ids: ['doc-1'],
    }

    render(<ResultsPanel result={result} auditId={12} />)

    // απουσία, όχι μήνυμα "δεν υπάρχει"
    expect(screen.queryByText('Συνολική κρίση (εκτός κατάταξης)')).not.toBeInTheDocument()
    expect(screen.getByText('Κορυφαίες ενότητες')).toBeInTheDocument()
  })

  it('passes refusal_reason through to the semantic answer and shows the refusal', () => {
    const result: SemanticResult = {
      mode: 'semantic',
      answer: 'Συνθετικό κείμενο άρνησης για δοκιμή.',
      citations: [],
      retrieved_doc_ids: [],
      model: 'precheck',
      routing_hint: null,
      refusal_reason: 'year_out_of_range',
    }

    render(<ResultsPanel result={result} auditId={11} />)

    expect(screen.getByTestId('refusal')).toBeInTheDocument()
    expect(screen.getByText(result.answer)).toBeInTheDocument()
    expect(screen.queryByText('Δεν βρέθηκαν δεδομένα στο εύρος')).not.toBeInTheDocument()
  })

  it('shows a placeholder when there is no result yet', () => {
    render(<ResultsPanel result={null} auditId={null} />)

    expect(screen.getByText('Υποβάλετε ένα ερώτημα για να δείτε αποτελέσματα')).toBeInTheDocument()
  })

  it('renders the structured citations like SemanticAnswer, with doc_id, page and section', () => {
    const result: StructuredResult = {
      mode: 'structured',
      data: { person_id: 'p1', period: '2012-09-14..2012-12-31', ea_type: 'Ε.Α.', score: 93 },
      citations: [{ doc_id: 'doc-a', page: 7, section: 'ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ' }],
      retrieved_doc_ids: ['doc-a'],
    }

    render(<ResultsPanel result={result} auditId={21} />)

    const citations = screen.getByTestId('citations')
    expect(citations).toHaveTextContent('doc-a')
    expect(citations).toHaveTextContent('σελίδα 7')
    expect(citations).toHaveTextContent('ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ')
  })

  it('shows "σελίδα δεν καταγράφηκε" when the page was not recorded, never blank', () => {
    const result: StructuredResult = {
      mode: 'structured',
      data: { person_id: 'p1', rows: [] },
      citations: [{ doc_id: 'doc-career', page: null, section: 'ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ' }],
      retrieved_doc_ids: ['doc-career'],
    }

    render(<ResultsPanel result={result} auditId={22} />)

    const citations = screen.getByTestId('citations')
    expect(citations).toHaveTextContent('σελίδα δεν καταγράφηκε')
    expect(citations).not.toHaveTextContent('σελίδα null')
    expect(citations).not.toHaveTextContent(/σελίδα\s*·/)
  })

  it('renders promotion rows verbatim, without fixing corrupted source values', () => {
    const result: StructuredResult = {
      mode: 'structured',
      data: {
        person_id: 'p1',
        rows: [
          {
            row_index: 0,
            rank: 'ΥΠΟΠΛΟΙΑΡΧΟΣ',
            promotion_date: '05/07/2013',
            decision_date: '02//02/04/2013',
            decision: 'ΠΕ ΠΑΜΨΗΦΕΙ ΓΙΑ ΤΟ ΈΤΟΣ 2019-2020',
            judged_for: null,
          },
        ],
      },
      citations: [{ doc_id: 'doc-career', page: null, section: 'ΚΡΙΣΕΙΣ ΠΡΟΑΓΩΓΩΝ' }],
      retrieved_doc_ids: ['doc-career'],
    }

    render(<ResultsPanel result={result} auditId={23} />)

    expect(screen.getByText('Κρίσεις προαγωγών')).toBeInTheDocument()
    expect(screen.getByText('02//02/04/2013')).toBeInTheDocument()
    expect(screen.getByText('05/07/2013')).toBeInTheDocument()
    expect(screen.getByText('ΠΕ ΠΑΜΨΗΦΕΙ ΓΙΑ ΤΟ ΈΤΟΣ 2019-2020')).toBeInTheDocument()
    expect(screen.getByText('ΥΠΟΠΛΟΙΑΡΧΟΣ')).toBeInTheDocument()
  })

  it('renders service time rows verbatim, months above 12 included', () => {
    const result: StructuredResult = {
      mode: 'structured',
      data: {
        person_id: 'p1',
        rows: [
          { row_index: 0, subsection: 'α', label: 'ΠΡΑΓΜΑΤΙΚΗ ΥΠΗΡΕΣΙΑ', years: 23, months: 0, days: 10 },
          { row_index: 1, subsection: 'β', label: 'ΈΤΟΣ', years: 7, months: 13, days: 8 },
        ],
      },
      citations: [{ doc_id: 'doc-career', page: null, section: 'ΣΥΝΟΛΙΚΟΣ ΧΡΟΝΟΣ ΥΠΗΡΕΣΙΑΣ' }],
      retrieved_doc_ids: ['doc-career'],
    }

    render(<ResultsPanel result={result} auditId={24} />)

    expect(screen.getByText('Συνολικός χρόνος υπηρεσίας')).toBeInTheDocument()
    expect(screen.getByText('ΠΡΑΓΜΑΤΙΚΗ ΥΠΗΡΕΣΙΑ')).toBeInTheDocument()
    expect(screen.getByText('ΈΤΟΣ')).toBeInTheDocument()
    expect(screen.getByText('13')).toBeInTheDocument()
    expect(screen.getByText('23')).toBeInTheDocument()
  })

  it('shows an empty state, not an empty table, for career rows with no entries', () => {
    const result: StructuredResult = {
      mode: 'structured',
      data: { person_id: 'p1', rows: [] },
      citations: [],
      retrieved_doc_ids: [],
    }

    render(<ResultsPanel result={result} auditId={25} />)

    expect(screen.getByText('Δεν βρέθηκαν εγγραφές')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.getByTestId('citations')).toHaveTextContent('Καμία παραπομπή')
  })
})
