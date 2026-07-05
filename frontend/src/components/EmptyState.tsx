interface EmptyStateProps {
  message?: string
}

export function EmptyState({ message = 'Δεν βρέθηκαν δεδομένα στο εύρος' }: EmptyStateProps) {
  return (
    <div
      className="rounded border border-dashed px-3 py-6 text-center text-sm"
      style={{ borderColor: '#26262d', color: '#6d6d78' }}
    >
      {message}
    </div>
  )
}
