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
      <span className="inline-flex items-center gap-2 text-[11.5px]" style={{ color: '#8b8b95' }}>
        <span className="h-1.75 w-1.75 rounded-full bg-gray-400" aria-hidden />
        Έλεγχος κατάστασης...
      </span>
    )
  }

  return (
    <span className="inline-flex items-center gap-2 text-[11.5px]">
      <span
        className="h-1.75 w-1.75 rounded-full"
        style={
          ollamaReachable
            ? { backgroundColor: '#3fdd78', boxShadow: '0 0 8px rgba(63,221,120,.6)' }
            : { backgroundColor: '#f59e0b' }
        }
        aria-hidden
      />
      {ollamaReachable ? (
        <span style={{ color: '#8b8b95' }}>Σύστημα ενεργό</span>
      ) : (
        <span style={{ color: '#f59e0b' }}>Ollama μη διαθέσιμο</span>
      )}
    </span>
  )
}
