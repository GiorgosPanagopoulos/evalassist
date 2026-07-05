import { useEffect, useState } from 'react'
import type { ApiClient } from '../api/client'

// Structural subset so tests can pass a plain Fake* object instead of a
// real ApiClient instance.
export type HealthIndicatorApi = Pick<ApiClient, 'getHealth'>

export function HealthIndicator({ api }: { api: HealthIndicatorApi }) {
  const [ollamaReachable, setOllamaReachable] = useState<boolean | null>(null)

  useEffect(() => {
    let cancelled = false
    api.getHealth().then((health) => {
      if (!cancelled) setOllamaReachable(health.ollama_reachable)
    })
    return () => {
      cancelled = true
    }
  }, [api])

  if (ollamaReachable === null) {
    return (
      <span className="inline-flex items-center gap-2 text-xs text-navy/50 dark:text-gold/50">
        <span className="h-2 w-2 rounded-full bg-gray-400" aria-hidden />
        Έλεγχος κατάστασης...
      </span>
    )
  }

  return (
    <span className="inline-flex items-center gap-2 text-xs">
      <span
        className={`h-2 w-2 rounded-full ${ollamaReachable ? 'bg-green-500' : 'bg-amber-500'}`}
        aria-hidden
      />
      {ollamaReachable ? (
        <span className="text-navy dark:text-gold">Ollama διαθέσιμο</span>
      ) : (
        <span className="text-amber-600 dark:text-amber-400">Ollama μη διαθέσιμο</span>
      )}
    </span>
  )
}
