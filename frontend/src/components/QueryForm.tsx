import { useEffect, useState, type SyntheticEvent } from 'react'
import type { ApiClient, ApiError } from '../api/client'
import type {
  PersonOut,
  SemanticResult,
  StructuredOperation,
  StructuredResult,
} from '../api/types'

type Mode = 'structured' | 'semantic'

// Structural subset so tests can pass a plain Fake* object instead of a
// real ApiClient instance (same fake-injection philosophy as the backend tests).
export type QueryFormApi = Pick<
  ApiClient,
  'getPersons' | 'getPeriods' | 'queryStructured' | 'querySemantic'
>

interface QueryFormProps {
  api: QueryFormApi
  onResult: (result: StructuredResult | SemanticResult, auditId: number) => void
  onError?: (error: ApiError) => void
}

const OPERATIONS: { value: StructuredOperation; label: string }[] = [
  { value: 'get_scores', label: 'Βαθμολογίες' },
  { value: 'compare_periods', label: 'Σύγκριση περιόδων' },
  { value: 'top_bottom_sections', label: 'Κορυφαίες / χαμηλότερες ενότητες' },
]

export function QueryForm({ api, onResult, onError }: QueryFormProps) {
  const [persons, setPersons] = useState<PersonOut[]>([])
  const [periods, setPeriods] = useState<string[]>([])
  const [personId, setPersonId] = useState('')
  const [period, setPeriod] = useState('')
  const [mode, setMode] = useState<Mode>('structured')
  const [operation, setOperation] = useState<StructuredOperation>('get_scores')
  const [otherPeriod, setOtherPeriod] = useState('')
  const [n, setN] = useState('')
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    api.getPersons().then(setPersons)
  }, [api])

  useEffect(() => {
    if (!personId) {
      setPeriods([])
      setPeriod('')
      return
    }
    api.getPeriods(personId).then((loaded) => {
      setPeriods(loaded)
      setPeriod('')
    })
  }, [api, personId])

  const questionTooShort = mode === 'semantic' && question.trim().length < 3
  const compareMissingOtherPeriod =
    mode === 'structured' && operation === 'compare_periods' && !otherPeriod

  const canSubmit = Boolean(personId) && Boolean(period) && !questionTooShort && !compareMissingOtherPeriod

  function handleOperationChange(next: StructuredOperation) {
    setOperation(next)
    setOtherPeriod('')
    setN('')
  }

  async function handleSubmit(e: SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!canSubmit || loading) return
    setLoading(true)
    setFormError(null)
    try {
      if (mode === 'structured') {
        const response = await api.queryStructured({
          person_id: personId,
          period,
          operation,
          ...(operation === 'compare_periods' ? { other_period: otherPeriod } : {}),
          ...(operation === 'top_bottom_sections' && n ? { n: Number(n) } : {}),
        })
        onResult(response.result, response.audit_id)
      } else {
        const response = await api.querySemantic({
          person_id: personId,
          period,
          question: question.trim(),
        })
        onResult(response.result, response.audit_id)
      }
    } catch (err) {
      const apiError = err as ApiError
      setFormError(apiError.detail ?? 'Σφάλμα')
      onError?.(apiError)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 rounded border border-navy/20 bg-white p-4 dark:border-gold/20 dark:bg-navy">
      <div className="flex gap-4">
        <label className="flex flex-1 flex-col gap-1 text-sm">
          Άτομο
          <select
            aria-label="Άτομο"
            value={personId}
            onChange={(e) => setPersonId(e.target.value)}
            className="rounded border border-navy/30 px-2 py-1 dark:border-gold/30 dark:bg-navy-light dark:text-white"
          >
            <option value="">Επιλέξτε άτομο</option>
            {persons.map((p) => (
              <option key={p.person_id} value={p.person_id}>
                {p.name} ({p.person_id})
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-1 flex-col gap-1 text-sm">
          Περίοδος
          <select
            aria-label="Περίοδος"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            disabled={!personId}
            className="rounded border border-navy/30 px-2 py-1 dark:border-gold/30 dark:bg-navy-light dark:text-white"
          >
            <option value="">Επιλέξτε περίοδο</option>
            {periods.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex gap-2" role="group" aria-label="Λειτουργία ερωτήματος">
        <button
          type="button"
          onClick={() => setMode('structured')}
          aria-pressed={mode === 'structured'}
          className={`flex-1 rounded px-3 py-1 text-sm font-medium ${
            mode === 'structured' ? 'bg-navy text-gold' : 'bg-navy/10 text-navy dark:bg-white/10 dark:text-white'
          }`}
        >
          Δομημένη
        </button>
        <button
          type="button"
          onClick={() => setMode('semantic')}
          aria-pressed={mode === 'semantic'}
          className={`flex-1 rounded px-3 py-1 text-sm font-medium ${
            mode === 'semantic' ? 'bg-navy text-gold' : 'bg-navy/10 text-navy dark:bg-white/10 dark:text-white'
          }`}
        >
          Σημασιολογική
        </button>
      </div>

      {mode === 'structured' ? (
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Λειτουργία
            <select
              aria-label="Λειτουργία"
              value={operation}
              onChange={(e) => handleOperationChange(e.target.value as StructuredOperation)}
              className="rounded border border-navy/30 px-2 py-1 dark:border-gold/30 dark:bg-navy-light dark:text-white"
            >
              {OPERATIONS.map((op) => (
                <option key={op.value} value={op.value}>
                  {op.label}
                </option>
              ))}
            </select>
          </label>

          {operation === 'compare_periods' && (
            <label className="flex flex-col gap-1 text-sm">
              Περίοδος σύγκρισης
              <select
                aria-label="Περίοδος σύγκρισης"
                value={otherPeriod}
                onChange={(e) => setOtherPeriod(e.target.value)}
                className="rounded border border-navy/30 px-2 py-1 dark:border-gold/30 dark:bg-navy-light dark:text-white"
              >
                <option value="">Επιλέξτε περίοδο</option>
                {periods
                  .filter((p) => p !== period)
                  .map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
              </select>
            </label>
          )}

          {operation === 'top_bottom_sections' && (
            <label className="flex flex-col gap-1 text-sm">
              Αριθμός ενοτήτων (n)
              <input
                aria-label="Αριθμός ενοτήτων"
                type="number"
                min={1}
                value={n}
                onChange={(e) => setN(e.target.value)}
                className="rounded border border-navy/30 px-2 py-1 dark:border-gold/30 dark:bg-navy-light dark:text-white"
              />
            </label>
          )}
        </div>
      ) : (
        <label className="flex flex-col gap-1 text-sm">
          Ερώτηση
          <textarea
            aria-label="Ερώτηση"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={3}
            className="rounded border border-navy/30 px-2 py-1 dark:border-gold/30 dark:bg-navy-light dark:text-white"
          />
          {questionTooShort && question.length > 0 && (
            <span className="text-xs text-red-600">Η ερώτηση απαιτεί τουλάχιστον 3 χαρακτήρες</span>
          )}
        </label>
      )}

      {formError && <p className="text-sm text-red-600">{formError}</p>}

      <button
        type="submit"
        disabled={!canSubmit || loading}
        className="rounded bg-gold px-4 py-2 font-semibold text-navy disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? 'Αποστολή...' : 'Υποβολή ερωτήματος'}
      </button>
    </form>
  )
}
