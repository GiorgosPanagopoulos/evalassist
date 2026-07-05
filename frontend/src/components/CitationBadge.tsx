import type { Citation } from '../api/types'

export function CitationBadge({ citation }: { citation: Citation }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded border px-2 py-1 font-mono text-xs"
      style={{ borderColor: '#26262d', backgroundColor: '#131318', color: '#8b8b95' }}
    >
      <span className="font-semibold">{citation.doc_id}</span>
      <span aria-hidden>·</span>
      <span>σελίδα {citation.page}</span>
      <span aria-hidden>·</span>
      <span>{citation.section}</span>
    </span>
  )
}
