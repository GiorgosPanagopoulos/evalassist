interface RoutingHintBannerProps {
  onDismiss: () => void
}

export function RoutingHintBanner({ onDismiss }: RoutingHintBannerProps) {
  return (
    <div
      role="note"
      aria-label="Πρόταση δρομολόγησης ερωτήματος"
      className="flex items-center justify-between gap-3 rounded border-l-4 px-3 py-2 text-sm"
      style={{ borderLeftColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', color: '#f2f2f4' }}
    >
      <span>Το ερώτημα αφορά βαθμολογία - δοκιμάστε Δομημένη αναζήτηση</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Απόρριψη πρότασης"
        className="shrink-0 text-xs font-semibold"
        style={{ color: '#8b8b95' }}
      >
        ✕
      </button>
    </div>
  )
}
