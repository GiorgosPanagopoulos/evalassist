interface EmptyStateProps {
  message?: string
}

export function EmptyState({ message = 'Δεν βρέθηκαν δεδομένα στο εύρος' }: EmptyStateProps) {
  return (
    <div className="rounded border border-dashed border-navy/30 px-3 py-6 text-center text-sm text-navy/60 dark:border-gold/30 dark:text-gold/60">
      {message}
    </div>
  )
}
