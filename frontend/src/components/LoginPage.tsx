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

export type LoginPageApi = Pick<ApiClient, 'login'>

interface LoginPageProps {
  api: LoginPageApi
  onLoggedIn: (me: Me) => void
}

export function LoginPage({ api, onLoggedIn }: LoginPageProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const me = await api.login(username, password)
      onLoggedIn(me)
    } catch (err) {
      setPassword('')
      setError(err instanceof ApiError ? err.detail : 'Αποτυχία σύνδεσης')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center" style={{ backgroundColor: '#0a0a0c', padding: 16 }}>
      <form
        onSubmit={handleSubmit}
        className="flex w-full max-w-[360px] flex-col gap-3.5 rounded-xl border"
        style={CARD_STYLE}
        aria-label="Σύνδεση"
      >
        <div className="mb-1 flex items-center gap-2.5">
          <img
            src={`${import.meta.env.BASE_URL}logo.png`}
            alt="EvalAssist"
            className="h-7 w-7 rounded-full object-cover"
            style={{ backgroundColor: '#f7f4ec' }}
          />
          <h1 className="text-[15px] font-bold" style={{ color: '#f2f2f4' }}>
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
