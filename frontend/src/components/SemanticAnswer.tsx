import { useState } from 'react'
import type { Citation } from '../api/types'
import { CitationList } from './CitationBadge'
import { EmptyState } from './EmptyState'
import { ReviewBanner } from './ReviewBanner'
import { RoutingHintBanner } from './RoutingHintBanner'

interface SemanticAnswerProps {
  answer: string
  // Required (not optional) so a semantic answer without its citations block
  // cannot be rendered by the type system.
  citations: Citation[]
  auditId: number
  routingHint?: string | null
  // Precheck refusal code. The refusal text is the server's `answer`,
  // rendered verbatim; no code-to-text mapping here.
  refusalReason?: string | null
}

export function SemanticAnswer({ answer, citations, auditId, routingHint, refusalReason }: SemanticAnswerProps) {
  const isEmptyScope = citations.length === 0
  const [hintDismissed, setHintDismissed] = useState(false)

  if (refusalReason) {
    return (
      <div className="flex flex-col gap-3">
        <ReviewBanner />

        <div
          data-testid="refusal"
          className="flex flex-col gap-2 rounded border px-3 py-3 text-sm"
          style={{ borderColor: '#2a3756' }}
        >
          <p className="font-semibold" style={{ color: '#e6eaf2' }}>
            Το ερώτημα δεν εκτελέστηκε
          </p>
          <p className="leading-relaxed" style={{ color: '#e6eaf2' }}>
            {answer}
          </p>
          <p className="font-mono text-xs" style={{ color: '#a9b4c8' }}>
            Αιτία: {refusalReason}
          </p>
        </div>

        <p className="font-mono text-xs" style={{ color: '#a9b4c8' }}>
          Καταχώρηση ελέγχου: #{auditId}
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {routingHint === 'structured' && !hintDismissed && (
        <RoutingHintBanner onDismiss={() => setHintDismissed(true)} />
      )}
      <ReviewBanner />

      {isEmptyScope ? (
        <EmptyState />
      ) : (
        <p className="text-sm leading-relaxed" style={{ color: '#e6eaf2' }}>
          {answer}
        </p>
      )}

      <CitationList citations={citations} />

      <p className="font-mono text-xs" style={{ color: '#a9b4c8' }}>
        Καταχώρηση ελέγχου: #{auditId}
      </p>
    </div>
  )
}
