import { useState } from 'react'
import type { Citation } from '../api/types'
import { CitationBadge } from './CitationBadge'
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
}

export function SemanticAnswer({ answer, citations, auditId, routingHint }: SemanticAnswerProps) {
  const isEmptyScope = citations.length === 0
  const [hintDismissed, setHintDismissed] = useState(false)

  return (
    <div className="flex flex-col gap-3">
      {routingHint === 'structured' && !hintDismissed && (
        <RoutingHintBanner onDismiss={() => setHintDismissed(true)} />
      )}
      <ReviewBanner />

      {isEmptyScope ? (
        <EmptyState />
      ) : (
        <p className="text-sm leading-relaxed" style={{ color: '#f2f2f4' }}>
          {answer}
        </p>
      )}

      <div data-testid="citations" className="flex flex-wrap gap-2">
        {citations.length === 0 ? (
          <span className="text-xs" style={{ color: '#8b8b95' }}>
            Καμία παραπομπή
          </span>
        ) : (
          citations.map((citation, idx) => (
            <CitationBadge key={`${citation.doc_id}-${citation.page}-${idx}`} citation={citation} />
          ))
        )}
      </div>

      <p className="font-mono text-xs" style={{ color: '#8b8b95' }}>
        Καταχώρηση ελέγχου: #{auditId}
      </p>
    </div>
  )
}
