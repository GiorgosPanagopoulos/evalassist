import type { Citation } from '../api/types'
import { CitationBadge } from './CitationBadge'
import { EmptyState } from './EmptyState'
import { ReviewBanner } from './ReviewBanner'

interface SemanticAnswerProps {
  answer: string
  // Required (not optional) so a semantic answer without its citations block
  // cannot be rendered by the type system.
  citations: Citation[]
  auditId: number
}

export function SemanticAnswer({ answer, citations, auditId }: SemanticAnswerProps) {
  const isEmptyScope = citations.length === 0

  return (
    <div className="flex flex-col gap-3">
      <ReviewBanner />

      {isEmptyScope ? (
        <EmptyState />
      ) : (
        <p className="text-sm leading-relaxed">{answer}</p>
      )}

      <div data-testid="citations" className="flex flex-wrap gap-2">
        {citations.length === 0 ? (
          <span className="text-xs text-navy/50 dark:text-gold/50">Καμία παραπομπή</span>
        ) : (
          citations.map((citation, idx) => (
            <CitationBadge key={`${citation.doc_id}-${citation.page}-${idx}`} citation={citation} />
          ))
        )}
      </div>

      <p className="font-mono text-xs text-navy/60 dark:text-gold/60">Καταχώρηση ελέγχου: #{auditId}</p>
    </div>
  )
}
