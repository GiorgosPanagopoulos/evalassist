import { useCallback, useEffect, useState } from 'react'
import { ApiClient, ApiError } from './api/client'
import type { Me, SemanticResult, StructuredResult } from './api/types'
import { QueryForm } from './components/QueryForm'
import { ResultsPanel } from './components/ResultsPanel'
import { HealthIndicator } from './components/HealthIndicator'
import { TimelinePanel } from './components/TimelinePanel'
import { LoginPage } from './components/LoginPage'
import { ChangePasswordPage } from './components/ChangePasswordPage'
import { UserAdminPanel } from './components/UserAdminPanel'
import { SECONDARY_BUTTON_CLASS, SECONDARY_BUTTON_STYLE } from './components/authStyles'

const defaultApi = new ApiClient()

// Τα logo είναι στο public/: σχετικά ως προς το base του build ('./'), ώστε
// να δουλεύουν και κάτω από subpath (π.χ. /evalassist/).
const ASSET_BASE = import.meta.env.BASE_URL

type AuthState = { status: 'loading' } | { status: 'anonymous' } | { status: 'authenticated'; me: Me }

type View = 'queries' | 'users' | 'password'

function MainEmptyState() {
  return (
    <div className="flex h-full flex-1 flex-col items-center justify-center gap-3.5 text-center">
      <p className="text-[13px]" style={{ color: '#6d6d78' }}>
        Υποβάλετε ένα ερώτημα για να δείτε αποτελέσματα
      </p>
    </div>
  )
}

function Brand() {
  return (
    <div className="mb-5 flex items-center gap-2.5">
      <img
        src={`${ASSET_BASE}logo.png`}
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
  )
}

interface WorkspaceProps {
  api: ApiClient
  me: Me
  onLogout: () => void
  onPasswordChanged: () => void
}

function Workspace({ api, me, onLogout, onPasswordChanged }: WorkspaceProps) {
  const [result, setResult] = useState<StructuredResult | SemanticResult | null>(null)
  const [auditId, setAuditId] = useState<number | null>(null)
  const [modeLabel, setModeLabel] = useState('βαθμολογίες')
  const [view, setView] = useState<View>('queries')

  function handleResult(result: StructuredResult | SemanticResult, auditId: number) {
    setResult(result)
    setAuditId(auditId)
    setView('queries')
  }

  function handleError(error: ApiError) {
    setResult(null)
    setAuditId(null)
    console.error(error)
  }

  const crumb = view === 'users' ? 'χρήστες' : view === 'password' ? 'αλλαγή κωδικού' : modeLabel

  return (
    <div className="grid min-h-screen" style={{ gridTemplateColumns: 'minmax(220px, 300px) 1fr', backgroundColor: '#0a0a0c' }}>
      <aside
        className="flex h-full flex-col"
        style={{ backgroundColor: '#0e0e11', borderRight: '1px solid #1d1d22', padding: '22px 20px' }}
      >
        <Brand />

        <QueryForm
          api={api}
          onResult={handleResult}
          onError={handleError}
          onModeLabelChange={setModeLabel}
          // Χωρίς features από τον server η επιλογή μένει κλειστή.
          semanticEnabled={me.features?.semantic_enabled === true}
        />
      </aside>

      <div
        className="relative flex flex-col overflow-hidden"
        style={{ background: 'radial-gradient(ellipse at 50% 40%, #131316 0%, #0a0a0c 70%)' }}
      >
        <img
          src={`${ASSET_BASE}logo-watermark.png`}
          alt=""
          aria-hidden="true"
          className="pointer-events-none select-none absolute top-1/2 left-1/2 z-0 -translate-x-1/2 -translate-y-1/2"
          style={{ width: 360, opacity: 0.18, filter: 'grayscale(0.4)' }}
        />

        <header
          className="relative z-10 flex items-center justify-between gap-4"
          style={{ padding: '16px 24px', borderBottom: '1px solid #1d1d22' }}
        >
          <div className="font-mono text-[12px]">
            <span style={{ color: '#8b8b95' }}>{view === 'queries' ? 'queries / ' : 'λογαριασμός / '}</span>
            <span style={{ color: '#f2f2f4' }}>{crumb}</span>
          </div>
          <div className="flex items-center gap-3">
            <HealthIndicator api={api} />
            <span className="font-mono text-[11.5px]" style={{ color: '#c9c9d1' }} aria-label="Συνδεδεμένος χρήστης">
              {me.username}
            </span>
            {view !== 'queries' && (
              <button type="button" onClick={() => setView('queries')} className={SECONDARY_BUTTON_CLASS} style={SECONDARY_BUTTON_STYLE}>
                Ερωτήματα
              </button>
            )}
            {me.role === 'admin' && view !== 'users' && (
              <button type="button" onClick={() => setView('users')} className={SECONDARY_BUTTON_CLASS} style={SECONDARY_BUTTON_STYLE}>
                Χρήστες
              </button>
            )}
            {view !== 'password' && (
              <button type="button" onClick={() => setView('password')} className={SECONDARY_BUTTON_CLASS} style={SECONDARY_BUTTON_STYLE}>
                Κωδικός
              </button>
            )}
            <button type="button" onClick={onLogout} className={SECONDARY_BUTTON_CLASS} style={SECONDARY_BUTTON_STYLE}>
              Αποσύνδεση
            </button>
          </div>
        </header>

        <div className="relative z-10 flex flex-1 flex-col overflow-y-auto">
          {view === 'users' && me.role === 'admin' ? (
            <div className="mx-auto w-full max-w-[1100px]" style={{ padding: '24px' }}>
              <UserAdminPanel api={api} />
            </div>
          ) : view === 'password' ? (
            <ChangePasswordPage
              api={api}
              forced={false}
              onChanged={() => {
                setView('queries')
                onPasswordChanged()
              }}
              onCancel={() => setView('queries')}
            />
          ) : (
            <>
              <div className="mx-auto w-full max-w-[1100px]" style={{ padding: '24px 24px 0' }}>
                <TimelinePanel api={api} />
              </div>
              {result === null ? <MainEmptyState /> : (
                <div className="mx-auto w-full max-w-[1100px]" style={{ padding: '24px' }}>
                  <ResultsPanel result={result} auditId={auditId} />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function App({ api = defaultApi }: { api?: ApiClient }) {
  const [auth, setAuth] = useState<AuthState>({ status: 'loading' })

  useEffect(() => {
    // Κάθε 401 (λήξη, logout από άλλη καρτέλα, απενεργοποίηση) γυρίζει στο login.
    api.setUnauthorizedHandler(() => setAuth({ status: 'anonymous' }))
    api
      .me()
      .then((me) => setAuth({ status: 'authenticated', me }))
      .catch(() => setAuth({ status: 'anonymous' }))
    return () => api.setUnauthorizedHandler(null)
  }, [api])

  const handleLogout = useCallback(() => {
    api
      .logout()
      .catch(() => undefined)
      .finally(() => setAuth({ status: 'anonymous' }))
  }, [api])

  const markPasswordChanged = useCallback(() => {
    setAuth((prev) =>
      prev.status === 'authenticated' ? { status: 'authenticated', me: { ...prev.me, must_change_pw: false } } : prev,
    )
  }, [])

  if (auth.status === 'loading') {
    return <div className="min-h-screen" style={{ backgroundColor: '#0a0a0c' }} aria-busy="true" />
  }

  if (auth.status === 'anonymous') {
    return <LoginPage api={api} onLoggedIn={(me) => setAuth({ status: 'authenticated', me })} />
  }

  if (auth.me.must_change_pw) {
    return (
      <div className="flex min-h-screen flex-col" style={{ backgroundColor: '#0a0a0c' }}>
        <ChangePasswordPage api={api} forced onChanged={markPasswordChanged} onLogout={handleLogout} />
      </div>
    )
  }

  return <Workspace api={api} me={auth.me} onLogout={handleLogout} onPasswordChanged={markPasswordChanged} />
}

export default App
