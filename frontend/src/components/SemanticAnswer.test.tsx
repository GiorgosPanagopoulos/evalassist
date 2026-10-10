import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SemanticAnswer } from './SemanticAnswer'

// Synthetic data only: no real person, unit or doc_id.
const REFUSAL_TEXT = 'Συνθετικό κείμενο άρνησης για δοκιμή.'
const EMPTY_STATE_TEXT = 'Δεν βρέθηκαν δεδομένα στο εύρος'
const REFUSAL_LABEL = 'Το ερώτημα δεν εκτελέστηκε'

describe('SemanticAnswer', () => {
  it.each(['year_out_of_range', 'year_other_period', 'field_out_of_schema', 'unknown_future_code'])(
    'renders the server refusal text verbatim for refusal_reason=%s',
    (reason) => {
      render(
        <SemanticAnswer answer={REFUSAL_TEXT} citations={[]} auditId={9} refusalReason={reason} />,
      )

      expect(screen.getByTestId('refusal')).toBeInTheDocument()
      expect(screen.getByText(REFUSAL_TEXT)).toBeInTheDocument()
      expect(screen.getByText(REFUSAL_LABEL)).toBeInTheDocument()
      expect(screen.getByText(`Αιτία: ${reason}`)).toBeInTheDocument()
      expect(
        screen.getByText('Συμβουλευτικό περιεχόμενο - απαιτείται ανθρώπινη αξιολόγηση'),
      ).toBeInTheDocument()
      expect(screen.queryByText(EMPTY_STATE_TEXT)).not.toBeInTheDocument()
      expect(screen.queryByTestId('citations')).not.toBeInTheDocument()
      expect(screen.queryByText('Καμία παραπομπή')).not.toBeInTheDocument()
      expect(screen.getByText('Καταχώρηση ελέγχου: #9')).toBeInTheDocument()
    },
  )

  it.each([undefined, null])(
    'renders the EmptyState and no refusal when citations are empty and refusal_reason=%s',
    (reason) => {
      render(
        <SemanticAnswer answer="Συνθετική κενή απάντηση." citations={[]} auditId={3} refusalReason={reason} />,
      )

      expect(screen.getByText(EMPTY_STATE_TEXT)).toBeInTheDocument()
      expect(screen.queryByTestId('refusal')).not.toBeInTheDocument()
    },
  )

  it('renders a normal answer with citations unchanged and no refusal', () => {
    const answer = 'Συνθετική απάντηση με παραπομπή.'
    render(
      <SemanticAnswer
        answer={answer}
        citations={[{ doc_id: 'doc-synthetic-1', page: 2, section: 'Ενότητα Α', score: 0.7 }]}
        auditId={4}
        routingHint={null}
      />,
    )

    expect(screen.getByText(answer)).toBeInTheDocument()
    expect(screen.getByTestId('citations')).toBeInTheDocument()
    expect(screen.getByText(/doc-synthetic-1/)).toBeInTheDocument()
    expect(screen.getByText('Ενότητα Α')).toBeInTheDocument()
    expect(screen.queryByText(EMPTY_STATE_TEXT)).not.toBeInTheDocument()
    expect(screen.queryByTestId('refusal')).not.toBeInTheDocument()
  })
})
