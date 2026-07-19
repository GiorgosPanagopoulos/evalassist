import { useState } from 'react'
import { ApiClient, ApiError } from './api/client'
import type { SemanticResult, StructuredResult } from './api/types'
import { QueryForm } from './components/QueryForm'
import { ResultsPanel } from './components/ResultsPanel'
import { HealthIndicator } from './components/HealthIndicator'

const api = new ApiClient()

function MainEmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3.5 text-center">
      <p className="text-[13px]" style={{ color: '#6d6d78' }}>
        Υποβάλετε ένα ερώτημα για να δείτε αποτελέσματα
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
    <div className="grid min-h-screen" style={{ gridTemplateColumns: 'minmax(220px, 300px) 1fr', backgroundColor: '#0a0a0c' }}>
      <aside
        className="flex h-full flex-col"
        style={{ backgroundColor: '#0e0e11', borderRight: '1px solid #1d1d22', padding: '22px 20px' }}
      >
        <div className="mb-5 flex items-center gap-2.5">
          <img
            src="/logo.png"
            alt="EvalAssist"
            className="h-7 w-7 rounded-full object-cover"
            style={{ backgroundColor: '#f7f4ec', boxShadow: '0 0 0 1px #26262d' }}
          />
          <span className="text-[15px] font-bold" style={{ color: '#f2f2f4' }}>
            EvalAssist
          </span>
          <span
            className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[.5px]"
            style={{ backgroundColor: '#e8c34a', color: '#0a0a0c' }}
          >
            Beta
          </span>
        </div>

        <QueryForm api={api} onResult={handleResult} onError={handleError} onModeLabelChange={setModeLabel} />
      </aside>

      <div
        className="relative flex flex-col overflow-hidden"
        style={{ background: 'radial-gradient(ellipse at 50% 40%, #131316 0%, #0a0a0c 70%)' }}
      >
        <svg
          aria-hidden
          viewBox="0 0 200 200"
          className="pointer-events-none absolute top-1/2 left-1/2 z-0 h-[360px] w-[360px] -translate-x-1/2 -translate-y-1/2"
          style={{ opacity: 0.14 }}
        >
          <defs>
            <path id="emblem-ring" d="M 100,100 m -80,0 a 80,80 0 1,1 160,0 a 80,80 0 1,1 -160,0" />
          </defs>
          <circle cx="100" cy="100" r="92" fill="none" stroke="#f2f2f4" strokeWidth="1" />
          <circle cx="100" cy="100" r="80" fill="none" stroke="#f2f2f4" strokeWidth="1" />
          <circle cx="100" cy="100" r="46" fill="none" stroke="#f2f2f4" strokeWidth="1" />
          <text fill="#f2f2f4" fontSize="10" letterSpacing="4">
            <textPath href="#emblem-ring" startOffset="0%">
              EVALASSIST · EVALASSIST ·
            </textPath>
          </text>
          <g stroke="#f2f2f4" strokeWidth="2.2" fill="none" strokeLinecap="round">
            <line x1="100" y1="60" x2="100" y2="145" />
            <path d="M 82,60 C 82,78 118,78 118,60" />
            <line x1="82" y1="60" x2="82" y2="48" />
            <line x1="118" y1="60" x2="118" y2="48" />
            <line x1="100" y1="48" x2="100" y2="42" />
            <line x1="80" y1="145" x2="120" y2="145" />
          </g>
        </svg>

        <header
          className="relative z-10 flex items-center justify-between"
          style={{ padding: '16px 24px', borderBottom: '1px solid #1d1d22' }}
        >
          <div className="font-mono text-[12px]">
            <span style={{ color: '#8b8b95' }}>queries / </span>
            <span style={{ color: '#f2f2f4' }}>{modeLabel}</span>
          </div>
          <HealthIndicator api={api} />
        </header>

        <div className="relative z-10 flex-1">
          {result === null ? <MainEmptyState /> : (
            <div className="mx-auto w-full max-w-[1100px]" style={{ padding: '24px' }}>
              <ResultsPanel result={result} auditId={auditId} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default App
