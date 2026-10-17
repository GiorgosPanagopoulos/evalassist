import { useState, type FormEvent } from 'react'
import { ApiError, type ApiClient } from '../api/client'
import {
  CARD_STYLE,
  ERROR_STYLE,
  INPUT_CLASS,
  INPUT_STYLE,
  LABEL_CLASS,
  PRIMARY_BUTTON_CLASS,
  PRIMARY_BUTTON_STYLE,
  SECONDARY_BUTTON_CLASS,
  SECONDARY_BUTTON_STYLE,
} from './authStyles'

// Ίδιο όριο με το backend (app.auth.passwords.MIN_PASSWORD_LENGTH). Ο server
// ελέγχει ξανά, εδώ είναι μόνο για άμεσο μήνυμα.
const MIN_PASSWORD_LENGTH = 12

export type ChangePasswordApi = Pick<ApiClient, 'changePassword'>

interface ChangePasswordPageProps {
  api: ChangePasswordApi
  // true: προσωρινός κωδικός, η εφαρμογή δεν ανοίγει πριν την αλλαγή.
  forced: boolean
  onChanged: () => void
  onCancel?: () => void
  onLogout?: () => void
}

export function ChangePasswordPage({ api, forced, onChanged, onCancel, onLogout }: ChangePasswordPageProps) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (next.length < MIN_PASSWORD_LENGTH) {
      setError(`Ο νέος κωδικός πρέπει να έχει τουλάχιστον ${MIN_PASSWORD_LENGTH} χαρακτήρες.`)
      return
    }
    if (next !== confirm) {
      setError('Οι δύο νέοι κωδικοί δεν ταιριάζουν.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      await api.changePassword(current, next)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Αποτυχία αλλαγής κωδικού')
    } finally {
      setLoading(false)
    }
  }

  const fields: [string, string, string, (v: string) => void][] = [
    ['Τρέχων κωδικός', 'current-password', current, setCurrent],
    ['Νέος κωδικός', 'new-password', next, setNext],
    ['Επανάληψη νέου κωδικού', 'new-password', confirm, setConfirm],
  ]

  return (
    <div className="flex flex-1 items-center justify-center" style={{ padding: 16 }}>
      <form
        onSubmit={handleSubmit}
        className="flex w-full max-w-[380px] flex-col gap-3.5 rounded-xl border"
        style={CARD_STYLE}
        aria-label="Αλλαγή κωδικού"
      >
        <h1 className="text-[15px] font-bold" style={{ color: '#e6eaf2' }}>
          Αλλαγή κωδικού
        </h1>
        {forced && (
          <p className="text-[12.5px]" style={{ color: '#c4ccdb' }}>
            Πρέπει να αλλάξετε τον προσωρινό κωδικό πριν συνεχίσετε.
          </p>
        )}
        {fields.map(([label, autoComplete, value, setter]) => (
          <label key={label} className="flex flex-col gap-1.5">
            <span className={LABEL_CLASS}>{label}</span>
            <input
              aria-label={label}
              type="password"
              autoComplete={autoComplete}
              value={value}
              onChange={(e) => setter(e.target.value)}
              className={INPUT_CLASS}
              style={INPUT_STYLE}
              required
            />
          </label>
        ))}
        {error && (
          <p role="alert" className="text-[12px]" style={ERROR_STYLE}>
            {error}
          </p>
        )}
        <button type="submit" disabled={loading} className={PRIMARY_BUTTON_CLASS} style={PRIMARY_BUTTON_STYLE}>
          {loading ? 'Αποθήκευση...' : 'Αλλαγή κωδικού'}
        </button>
        <div className="flex justify-end gap-2">
          {onCancel && !forced && (
            <button type="button" onClick={onCancel} className={SECONDARY_BUTTON_CLASS} style={SECONDARY_BUTTON_STYLE}>
              Ακύρωση
            </button>
          )}
          {onLogout && (
            <button type="button" onClick={onLogout} className={SECONDARY_BUTTON_CLASS} style={SECONDARY_BUTTON_STYLE}>
              Αποσύνδεση
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
