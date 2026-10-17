import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { ApiError, type ApiClient } from '../api/client'
import type { UserOut } from '../api/types'
import {
  CARD_STYLE,
  ERROR_STYLE,
  INPUT_CLASS,
  INPUT_STYLE,
  LABEL_CLASS,
  SECONDARY_BUTTON_CLASS,
  SECONDARY_BUTTON_STYLE,
} from './authStyles'

export type UserAdminApi = Pick<ApiClient, 'listUsers' | 'createUser' | 'disableUser' | 'resetPassword'>

interface TempPassword {
  username: string
  password: string
}

function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.detail : fallback
}

function statusText(u: UserOut): string {
  if (!u.is_active) return 'ανενεργός'
  if (u.locked) return 'κλειδωμένος'
  if (u.must_change_pw) return 'αναμονή αλλαγής κωδικού'
  return 'ενεργός'
}

export function UserAdminPanel({ api }: { api: UserAdminApi }) {
  const [users, setUsers] = useState<UserOut[]>([])
  const [username, setUsername] = useState('')
  const [error, setError] = useState<string | null>(null)
  // Ο προσωρινός κωδικός ζει μόνο σε αυτό το state: εμφανίζεται μία φορά και
  // χάνεται με την επόμενη ενέργεια ή την έξοδο από τη σελίδα.
  const [temp, setTemp] = useState<TempPassword | null>(null)
  const [confirmDisable, setConfirmDisable] = useState<number | null>(null)

  const reload = useCallback(() => {
    api
      .listUsers()
      .then(setUsers)
      .catch((err) => setError(errorText(err, 'Αποτυχία φόρτωσης χρηστών')))
  }, [api])

  useEffect(() => {
    reload()
  }, [reload])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setTemp(null)
    try {
      // Το API δημιουργεί μόνο role='user'. Admins μόνο από το CLI (create_admin).
      const created = await api.createUser(username, 'user')
      setTemp({ username: created.username, password: created.temp_password })
      setUsername('')
      reload()
    } catch (err) {
      setError(errorText(err, 'Αποτυχία δημιουργίας χρήστη'))
    }
  }

  async function handleReset(u: UserOut) {
    setError(null)
    setTemp(null)
    try {
      const { temp_password } = await api.resetPassword(u.id)
      setTemp({ username: u.username, password: temp_password })
      reload()
    } catch (err) {
      setError(errorText(err, 'Αποτυχία επαναφοράς κωδικού'))
    }
  }

  async function handleDisable(u: UserOut) {
    setError(null)
    setTemp(null)
    setConfirmDisable(null)
    try {
      await api.disableUser(u.id)
      reload()
    } catch (err) {
      setError(errorText(err, 'Αποτυχία απενεργοποίησης'))
    }
  }

  return (
    <section className="flex flex-col gap-4 rounded-xl border" style={CARD_STYLE} aria-label="Διαχείριση χρηστών">
      <span className={LABEL_CLASS}>Διαχείριση χρηστών</span>

      <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3" aria-label="Νέος χρήστης">
        <label className="flex flex-col gap-1.5">
          <span className={LABEL_CLASS}>Νέος χρήστης</span>
          <input
            aria-label="Νέο όνομα χρήστη"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className={INPUT_CLASS}
            style={INPUT_STYLE}
            autoComplete="off"
            required
          />
        </label>
        <button type="submit" className={SECONDARY_BUTTON_CLASS} style={SECONDARY_BUTTON_STYLE}>
          Δημιουργία
        </button>
      </form>

      {temp && (
        <div
          role="status"
          className="rounded-lg border px-3 py-2 text-[12.5px]"
          style={{ borderColor: '#d4a93a', color: '#e6eaf2' }}
        >
          Προσωρινός κωδικός για <strong>{temp.username}</strong>:{' '}
          <code className="font-mono" style={{ color: '#d4a93a' }}>
            {temp.password}
          </code>
          <div className="mt-1 text-[11.5px]" style={{ color: '#a9b4c8' }}>
            Εμφανίζεται μόνο μία φορά. Δώστε τον στον χρήστη, που θα πρέπει να τον αλλάξει στην πρώτη σύνδεση.
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="text-[12px]" style={ERROR_STYLE}>
          {error}
        </p>
      )}

      <table className="w-full text-left text-[12.5px]" style={{ color: '#e6eaf2' }}>
        <thead>
          <tr className={LABEL_CLASS}>
            <th className="py-1.5">Χρήστης</th>
            <th className="py-1.5">Ρόλος</th>
            <th className="py-1.5">Κατάσταση</th>
            <th className="py-1.5" />
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} style={{ borderTop: '1px solid #1e2a44' }}>
              <td className="py-2 font-mono">{u.username}</td>
              <td className="py-2">{u.role}</td>
              <td className="py-2">{statusText(u)}</td>
              <td className="py-2">
                {/* Ο server απορρίπτει κάθε ενέργεια σε admin. Το UI απλώς δεν την προσφέρει. */}
                {u.role === 'user' && (
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => handleReset(u)}
                      className={SECONDARY_BUTTON_CLASS}
                      style={SECONDARY_BUTTON_STYLE}
                      aria-label={`Νέος προσωρινός κωδικός για ${u.username}`}
                    >
                      Νέος κωδικός
                    </button>
                    {u.is_active &&
                      (confirmDisable === u.id ? (
                        <button
                          type="button"
                          onClick={() => handleDisable(u)}
                          className={SECONDARY_BUTTON_CLASS}
                          style={{ ...SECONDARY_BUTTON_STYLE, color: '#f2a48f' }}
                          aria-label={`Επιβεβαίωση απενεργοποίησης ${u.username}`}
                        >
                          Επιβεβαίωση;
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setConfirmDisable(u.id)}
                          className={SECONDARY_BUTTON_CLASS}
                          style={SECONDARY_BUTTON_STYLE}
                          aria-label={`Απενεργοποίηση ${u.username}`}
                        >
                          Απενεργοποίηση
                        </button>
                      ))}
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
