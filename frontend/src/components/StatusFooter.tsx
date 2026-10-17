const VERSION = 'ΔΙΠΛΗΚΥΒ-Τμήματα Τεχνητής Νοημοσύνης & Αναλυτικής Δεδομένων · v1.0 · 2026'

export function StatusFooter({ items }: { items: (string | null)[] }) {
  const parts = [...items.filter((x): x is string => Boolean(x)), VERSION]
  return (
    <p data-testid="status-footer" className="font-mono text-[12px] leading-relaxed wrap-break-word text-subtle">
      {parts.map((part, i) => (
        <span key={i}>
          {i > 0 && <span aria-hidden="true"> · </span>}
          {part}
        </span>
      ))}
    </p>
  )
}
