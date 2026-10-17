import { useEffect, useState } from 'react'
import type { ApiClient } from '../api/client'

// Structural subset so tests can pass a plain Fake* object instead of a
// real ApiClient instance.
export type HealthIndicatorApi = Pick<ApiClient, 'getHealth'>

type HealthState = 'checking' | 'ok' | 'ollama_down' | 'system_down'

const GREEN_DOT = { backgroundColor: '#3fb68b', boxShadow: '0 0 8px rgba(63,182,139,.5)' }
const AMBER_DOT = { backgroundColor: '#f59e0b' }

// semanticEnabled έρχεται από το features.semantic_enabled του /api/auth/me,
// τη μόνη πηγή του flag. Το ollama_reachable του health μετρά μόνο με το
// semantic ανοιχτό: κλειστό σημαίνει ότι το Ollama δεν χρειάζεται, όχι βλάβη.
export function HealthIndicator({
  api,
  semanticEnabled,
}: {
  api: HealthIndicatorApi
  semanticEnabled: boolean
}) {
  const [state, setState] = useState<HealthState>('checking')

  useEffect(() => {
    let cancelled = false
    api
      .getHealth()
      .then((health) => {
        if (cancelled) return
        if (health.status !== 'ok') setState('system_down')
        else if (!semanticEnabled || health.ollama_reachable === true) setState('ok')
        else setState('ollama_down')
      })
      .catch(() => {
        // Network σφάλμα ή μη-2xx: το ίδιο το API δεν απαντά.
        if (!cancelled) setState('system_down')
      })
    return () => {
      cancelled = true
    }
  }, [api, semanticEnabled])

  if (state === 'checking') {
    return (
      <span className="inline-flex items-center gap-2 text-[11.5px]" style={{ color: '#a9b4c8' }}>
        <span className="h-1.75 w-1.75 rounded-full bg-gray-400" aria-hidden />
        Έλεγχος κατάστασης...
      </span>
    )
  }

  const ok = state === 'ok'
  return (
    <span className="inline-flex items-center gap-2 text-[11.5px]">
      <span
        className="h-1.75 w-1.75 rounded-full"
        style={ok ? GREEN_DOT : AMBER_DOT}
        data-testid="health-dot"
        aria-hidden
      />
      {ok ? (
        <span style={{ color: '#a9b4c8' }}>Σύστημα ενεργό</span>
      ) : (
        <span style={{ color: '#f59e0b' }}>
          {state === 'ollama_down' ? 'Ollama μη διαθέσιμο' : 'Σύστημα μη διαθέσιμο'}
        </span>
      )}
    </span>
  )
}
