import type { StructuredCitation } from '../api/types'

// Semantic και structured παραπομπές: το semantic Citation ταιριάζει δομικά.
// page `null` = η σελίδα δεν καταγράφηκε στη DB — ρητό κείμενο, ποτέ κενό.
export function CitationBadge({ citation }: { citation: StructuredCitation }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded border px-2 py-1 font-mono text-xs"
      style={{ borderColor: '#26262d', backgroundColor: '#131318', color: '#8b8b95' }}
    >
      <span className="font-semibold">{citation.doc_id}</span>
      <span aria-hidden>·</span>
      <span>{citation.page === null ? 'σελίδα δεν καταγράφηκε' : `σελίδα ${citation.page}`}</span>
      <span aria-hidden>·</span>
      <span>{citation.section}</span>
    </span>
  )
}

export function CitationList({ citations }: { citations: StructuredCitation[] }) {
  return (
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
  )
}
