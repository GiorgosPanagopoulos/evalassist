interface EmptyStateProps {
  message?: string
}

export function EmptyState({ message = 'Δεν βρέθηκαν δεδομένα στο εύρος' }: EmptyStateProps) {
  return (
    <div
      className="rounded border border-dashed px-3 py-6 text-center text-sm"
      style={{ borderColor: '#2a3756', color: '#7884a0' }}
    >
      {message}
    </div>
  )
}
