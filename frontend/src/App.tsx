import { useState } from 'react'
import { ApiClient, ApiError } from './api/client'
import type { SemanticResult, StructuredResult } from './api/types'
import { QueryForm } from './components/QueryForm'
import { ResultsPanel } from './components/ResultsPanel'
import { HealthIndicator } from './components/HealthIndicator'

const api = new ApiClient()

function App() {
  const [result, setResult] = useState<StructuredResult | SemanticResult | null>(null)
  const [auditId, setAuditId] = useState<number | null>(null)

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
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-6">
      <header className="flex items-center justify-between border-b border-navy/20 pb-4 dark:border-gold/20">
        <h1 className="text-xl font-bold text-navy dark:text-gold">EvalAssist</h1>
        <HealthIndicator api={api} />
      </header>

      <QueryForm api={api} onResult={handleResult} onError={handleError} />

      <ResultsPanel result={result} auditId={auditId} />
    </div>
  )
}

export default App
