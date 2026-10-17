import { useState, type FormEvent } from 'react'
import { ApiError, type ApiClient } from '../api/client'
import type { Me } from '../api/types'
import {
  CARD_STYLE,
  ERROR_STYLE,
  INPUT_CLASS,
  INPUT_STYLE,
  LABEL_CLASS,
  PRIMARY_BUTTON_CLASS,
  PRIMARY_BUTTON_STYLE,
} from './authStyles'

export type LoginPageApi = Pick<ApiClient, 'login' | 'me'>

export const INSECURE_CONTEXT_TEXT =
  'Η σύνδεση δεν είναι ασφαλής (HTTP). Η είσοδος δεν θα λειτουργήσει. Επικοινωνήστε με τον διαχειριστή.'
export const SESSION_NOT_STORED_TEXT =
  'Η συνεδρία δεν αποθηκεύτηκε. Βεβαιωθείτε ότι η πρόσβαση γίνεται μέσω HTTPS.'

interface LoginPageProps {
  api: LoginPageApi
  onLoggedIn: (me: Me) => void
  // Default: window.isSecureContext. Το localhost είναι secure context, άρα
  // στο dev δεν εμφανίζεται τίποτα.
  secureContext?: boolean
}

export function LoginPage({ api, onLoggedIn, secureContext = window.isSecureContext !== false }: LoginPageProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const loggedIn = await api.login(username, password)
      // Το session cookie είναι Secure: σε http ο browser δεν το κρατά και το
      // login πετυχαίνει χωρίς session. Ο έλεγχος το κάνει μήνυμα αντί για
      // σιωπηλή επιστροφή στο login με το πρώτο 401.
      let me = loggedIn
      try {
        me = await api.me({ ignoreUnauthorized: true })
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          setPassword('')
          setError(SESSION_NOT_STORED_TEXT)
          return
        }
        // 500 ή δίκτυο: ο έλεγχος δεν μπλοκάρει ένα login που πέτυχε.
      }
      onLoggedIn(me)
    } catch (err) {
      setPassword('')
      setError(err instanceof ApiError ? err.detail : 'Αποτυχία σύνδεσης')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center" style={{ backgroundColor: '#0b1220', padding: 16 }}>
      <img
        src={`${import.meta.env.BASE_URL}logo.png`}
        alt="EvalAssist"
        width={96}
        height={96}
        className="mb-6 h-24 w-24 rounded-full border-[1.5px] border-[#d4a93a] object-cover"
        style={{ backgroundColor: '#f7f4ec' }}
      />
      {!secureContext && (
        <p
          role="alert"
          data-testid="insecure-context"
          className="mb-4 w-full max-w-[360px] rounded-xl border px-4 py-3 text-[13px]"
          style={{ ...ERROR_STYLE, borderColor: '#5c2b22', backgroundColor: '#1f1214' }}
        >
          {INSECURE_CONTEXT_TEXT}
        </p>
      )}
      <form
        onSubmit={handleSubmit}
        className="flex w-full max-w-[360px] flex-col gap-3.5 rounded-xl border"
        style={CARD_STYLE}
        aria-label="Σύνδεση"
      >
        <div className="mb-1 flex items-center gap-2.5">
          <h1 className="text-[15px] font-bold" style={{ color: '#e6eaf2' }}>
            EvalAssist
          </h1>
        </div>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL_CLASS}>Όνομα χρήστη</span>
          <input
            aria-label="Όνομα χρήστη"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className={INPUT_CLASS}
            style={INPUT_STYLE}
            required
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL_CLASS}>Κωδικός</span>
          <input
            aria-label="Κωδικός"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={INPUT_CLASS}
            style={INPUT_STYLE}
            required
          />
        </label>
        {error && (
          <p role="alert" className="text-[12px]" style={ERROR_STYLE}>
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={loading || !username || !password}
          className={PRIMARY_BUTTON_CLASS}
          style={PRIMARY_BUTTON_STYLE}
        >
          {loading ? 'Σύνδεση...' : 'Σύνδεση'}
        </button>
      </form>
    </div>
  )
}
