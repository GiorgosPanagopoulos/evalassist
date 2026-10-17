import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiClient, ApiError } from './api/client'
import type { Me, PersonOut, SemanticResult, StructuredResult } from './api/types'
import { QueryForm } from './components/QueryForm'
import { ResultsPanel } from './components/ResultsPanel'
import { HealthIndicator } from './components/HealthIndicator'
import { TimelinePanel } from './components/TimelinePanel'
import { LoginPage } from './components/LoginPage'
import { ChangePasswordPage } from './components/ChangePasswordPage'
import { UserAdminPanel } from './components/UserAdminPanel'
import { IconRail, type View } from './components/IconRail'
import type { QueryMode } from './components/ModeBadge'
import { uiFlags } from './lib/flags'

const defaultApi = new ApiClient()

type AuthState = { status: 'loading' } | { status: 'anonymous' } | { status: 'authenticated'; me: Me }

interface WorkspaceProps {
  api: ApiClient
  me: Me
  onLogout: () => void
  onPasswordChanged: () => void
}

function Workspace({ api, me, onLogout, onPasswordChanged }: WorkspaceProps) {
  const flags = uiFlags(me.features)
  const [result, setResult] = useState<StructuredResult | SemanticResult | null>(null)
  const [auditId, setAuditId] = useState<number | null>(null)
  const [mode, setMode] = useState<QueryMode>('structured')
  const [view, setView] = useState<View>('queries')
  const [timelineKey, setTimelineKey] = useState(0)
  // Μία πηγή αλήθειας για το άτομο: η αναζήτηση του toolbar. Το ref κρατά
  // το τρέχον person_id για σύγκριση με απαντήσεις που φτάνουν αργά.
  const [selectedPerson, setSelectedPerson] = useState<PersonOut | null>(null)
  const selectedPersonIdRef = useRef('')

  function handlePersonChange(person: PersonOut | null) {
    selectedPersonIdRef.current = person?.person_id ?? ''
    setSelectedPerson(person)
    // Ποτέ στοιχεία δύο ατόμων μαζί: τα αποτελέσματα του προηγούμενου φεύγουν.
    setResult(null)
    setAuditId(null)
  }

  function handleResult(result: StructuredResult | SemanticResult, auditId: number, personId: string) {
    // Απάντηση για άτομο που δεν είναι πια επιλεγμένο (π.χ. semantic που
    // ολοκληρώθηκε μετά την αλλαγή ατόμου): απορρίπτεται, δεν εμφανίζεται.
    if (personId !== selectedPersonIdRef.current) return
    setResult(result)
    setAuditId(auditId)
    setView('queries')
  }

  function handleTimelineRequest() {
    setResult(null)
    setAuditId(null)
    setView('queries')
    setTimelineKey((k) => k + 1)
  }

  function handleError(error: ApiError) {
    setResult(null)
    setAuditId(null)
    console.error(error)
  }

  return (
    <div className="flex min-h-screen flex-col bg-bg md:flex-row">
      <IconRail me={me} view={view} flags={flags} onNavigate={setView} onLogout={onLogout} />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print border-b border-line bg-toolbar px-4 py-3 sm:px-6 lg:px-8">
          <QueryForm
            api={api}
            personId={selectedPerson?.person_id ?? ''}
            onPersonChange={handlePersonChange}
            onResult={handleResult}
            onError={handleError}
            onModeChange={setMode}
            onTimelineRequest={handleTimelineRequest}
            // Χωρίς features από τον server η επιλογή μένει κλειστή.
            semanticEnabled={flags.semantic}
            trailing={<HealthIndicator api={api} semanticEnabled={flags.semantic} />}
          />
        </header>

        <main className="flex flex-1 flex-col">
          {view === 'users' && me.role === 'admin' ? (
            <div className="mx-auto w-full max-w-[1100px] p-4 sm:p-6">
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
            <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-6 px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
              <TimelinePanel
                api={api}
                person={selectedPerson}
                mode={mode}
                flags={flags}
                reloadKey={timelineKey}
              />
              {result !== null && selectedPerson !== null && (
                <ResultsPanel result={result} auditId={auditId} person={selectedPerson} />
              )}
            </div>
          )}
        </main>
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
    return <div className="min-h-screen bg-bg" aria-busy="true" />
  }

  if (auth.status === 'anonymous') {
    return <LoginPage api={api} onLoggedIn={(me) => setAuth({ status: 'authenticated', me })} />
  }

  if (auth.me.must_change_pw) {
    return (
      <div className="flex min-h-screen flex-col bg-bg">
        <ChangePasswordPage api={api} forced onChanged={markPasswordChanged} onLogout={handleLogout} />
      </div>
    )
  }

  return <Workspace api={api} me={auth.me} onLogout={handleLogout} onPasswordChanged={markPasswordChanged} />
}

export default App
