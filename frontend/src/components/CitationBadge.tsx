import type { Citation } from '../api/types'

export function CitationBadge({ citation }: { citation: Citation }) {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-gold/50 bg-navy/5 px-2 py-1 font-mono text-xs text-navy dark:bg-white/5 dark:text-gold">
      <span className="font-semibold">{citation.doc_id}</span>
      <span aria-hidden>·</span>
      <span>σελίδα {citation.page}</span>
      <span aria-hidden>·</span>
      <span>{citation.section}</span>
    </span>
  )
}
