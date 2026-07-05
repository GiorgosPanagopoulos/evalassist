import { useState } from 'react'
import { ApiClient, ApiError } from './api/client'
import type { SemanticResult, StructuredResult } from './api/types'
import { QueryForm } from './components/QueryForm'
import { ResultsPanel } from './components/ResultsPanel'
import { HealthIndicator } from './components/HealthIndicator'

const api = new ApiClient()

function MainEmptyState() {
  return (
    <div
      className="flex h-full flex-col items-center justify-center gap-3.5 text-center"
      style={{ background: 'radial-gradient(ellipse at 50% 40%, #131316 0%, #0a0a0c 70%)' }}
    >
      <div
        className="flex h-11 w-11 items-center justify-center rounded-xl border"
        style={{ borderColor: '#26262d' }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4a4a55" strokeWidth="2" aria-hidden>
          <circle cx="11" cy="11" r="7" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
      </div>
      <p className="text-[13px]" style={{ color: '#6d6d78' }}>
        Υποβάλετε ένα ερώτημα για να δείτε αποτελέσματα
      </p>
      <p className="font-mono text-[11px]" style={{ color: '#4a4a55' }}>
        ⌘K για γρήγορη αναζήτηση
      </p>
    </div>
  )
}

function App() {
  const [result, setResult] = useState<StructuredResult | SemanticResult | null>(null)
  const [auditId, setAuditId] = useState<number | null>(null)
  const [modeLabel, setModeLabel] = useState('βαθμολογίες')

  function handleResult(result: StructuredResult | SemanticResult, auditId: number) {
    setResult(result)
    setAuditId(auditId)
  }

  function handleError(error: ApiError) {
    setResult(null)
    setAuditId(null)
    console.error(error)
  }

  return (
    <div className="grid min-h-screen" style={{ gridTemplateColumns: '300px 1fr', backgroundColor: '#0a0a0c' }}>
      <aside
        className="flex h-full flex-col"
        style={{ backgroundColor: '#0e0e11', borderRight: '1px solid #1d1d22', padding: '22px 20px' }}
      >
        <div className="mb-5 flex items-center gap-2.5">
          <div
            className="flex h-6.5 w-6.5 items-center justify-center rounded-[7px] font-mono font-bold"
            style={{ background: 'linear-gradient(135deg, #7c5cff, #4de3ff)', color: '#0a0a0c' }}
          >
            E
          </div>
          <span className="text-[15px] font-bold" style={{ color: '#f2f2f4' }}>
            EvalAssist
          </span>
        </div>

        <QueryForm api={api} onResult={handleResult} onError={handleError} onModeLabelChange={setModeLabel} />
      </aside>

      <div className="flex flex-col">
        <header
          className="flex items-center justify-between"
          style={{ padding: '16px 24px', borderBottom: '1px solid #1d1d22' }}
        >
          <div className="font-mono text-[12px]">
            <span style={{ color: '#8b8b95' }}>queries / </span>
            <span style={{ color: '#f2f2f4' }}>{modeLabel}</span>
          </div>
          <HealthIndicator api={api} />
        </header>

        <div className="flex-1">
          {result === null ? <MainEmptyState /> : (
            <div style={{ padding: '24px' }}>
              <ResultsPanel result={result} auditId={auditId} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default App
