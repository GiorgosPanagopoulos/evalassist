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
  onModeLabelChange?: (label: string) => void
}

const OPERATIONS: { value: StructuredOperation; label: string }[] = [
  { value: 'get_scores', label: 'Βαθμολογίες' },
  { value: 'compare_periods', label: 'Σύγκριση περιόδων' },
  { value: 'top_bottom_sections', label: 'Κορυφαίες / χαμηλότερες ενότητες' },
]

const MODE_LABELS: Record<StructuredOperation, string> = {
  get_scores: 'βαθμολογίες',
  compare_periods: 'σύγκριση περιόδων',
  top_bottom_sections: 'κορυφαίες / χαμηλότερες ενότητες',
}

const LABEL_CLASS = 'text-[11px] font-semibold uppercase tracking-[.6px] text-[#8b8b95]'

const SELECT_CLASS =
  'rounded-lg border border-[#26262d] py-2.5 pl-3 pr-8 text-[13px] appearance-none bg-no-repeat bg-[right_12px_center] transition-colors duration-[120ms]'

const FIELD_CLASS = 'rounded-lg border border-[#26262d] px-3 py-2.5 text-[13px] transition-colors duration-[120ms]'

const ACTIVE_SEGMENT_STYLE = {
  backgroundColor: '#26262d',
  color: '#f2f2f4',
  boxShadow: '0 1px 3px rgba(0,0,0,.4)',
}

const ACTIVE_SEMANTIC_SEGMENT_STYLE = {
  backgroundColor: '#26262d',
  color: '#f2f2f4',
  boxShadow: '0 1px 3px rgba(0,0,0,.4), 0 0 0 1.5px #4de3ff',
  borderRadius: '6px',
}

const INACTIVE_SEGMENT_STYLE = { backgroundColor: 'transparent', color: '#8b8b95' }

const CHEVRON_BG = {
  backgroundImage:
    "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6' fill='none'%3E%3Cpath d='M1 1L5 5L9 1' stroke='%234a4a55' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")",
}

export function QueryForm({ api, onResult, onError, onModeLabelChange }: QueryFormProps) {
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
    onModeLabelChange?.(mode === 'semantic' ? 'σημασιολογική' : MODE_LABELS[operation])
  }, [mode, operation, onModeLabelChange])

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

  const selectStyle = (value: string) => ({
    backgroundColor: '#131318',
    color: value ? '#f2f2f4' : '#6d6d78',
    ...CHEVRON_BG,
  })

  const personSelectStyle = (value: string) => ({
    backgroundColor: '#131318',
    color: value ? '#f2f2f4' : '#e8e8ec',
    fontFamily: value ? undefined : 'var(--font-mono)',
    ...CHEVRON_BG,
  })

  const fieldStyle = { backgroundColor: '#131318', color: '#f2f2f4' }

  return (
    <form onSubmit={handleSubmit} className="flex flex-1 flex-col gap-3.5">
      <label className="flex flex-col gap-1.5">
        <span className={LABEL_CLASS}>Άτομο</span>
        <select
          aria-label="Άτομο"
          value={personId}
          onChange={(e) => setPersonId(e.target.value)}
          className={SELECT_CLASS}
          style={personSelectStyle(personId)}
        >
          <option value="">Μ-00000</option>
          {persons.map((p) => (
            <option key={p.person_id} value={p.person_id}>
              {p.name ? `${p.name} (${p.person_id})` : `(${p.person_id})`}
            </option>
          ))}
        </select>
      </label>

      {mode === 'structured' && operation === 'compare_periods' ? (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1.5">
            <span className={LABEL_CLASS}>Από</span>
            <select
              aria-label="Από"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              disabled={!personId}
              className={SELECT_CLASS}
              style={selectStyle(period)}
            >
              <option value="">Επιλέξτε περίοδο</option>
              {periods.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className={LABEL_CLASS}>Έως</span>
            <select
              aria-label="Έως"
              value={otherPeriod}
              onChange={(e) => setOtherPeriod(e.target.value)}
              disabled={!personId}
              className={SELECT_CLASS}
              style={selectStyle(otherPeriod)}
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
        </div>
      ) : (
        <label className="flex flex-col gap-1.5">
          <span className={LABEL_CLASS}>Περίοδος</span>
          <select
            aria-label="Περίοδος"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            disabled={!personId}
            className={SELECT_CLASS}
            style={selectStyle(period)}
          >
            <option value="">Επιλέξτε περίοδο</option>
            {periods.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="flex flex-col gap-1.5">
        <span className={LABEL_CLASS}>Τύπος</span>
        <div
          className="flex rounded-lg border p-[3px]"
          style={{ backgroundColor: '#131318', borderColor: '#26262d' }}
          role="group"
          aria-label="Τύπος ερωτήματος"
        >
          <button
            type="button"
            onClick={() => setMode('structured')}
            aria-pressed={mode === 'structured'}
            className="flex-1 rounded-md px-3 py-1.5 text-[12px] font-semibold"
            style={mode === 'structured' ? ACTIVE_SEGMENT_STYLE : INACTIVE_SEGMENT_STYLE}
          >
            Δομημένη
          </button>
          <button
            type="button"
            onClick={() => setMode('semantic')}
            aria-pressed={mode === 'semantic'}
            className="flex-1 rounded-md px-3 py-1.5 text-[12px] font-semibold"
            style={mode === 'semantic' ? ACTIVE_SEMANTIC_SEGMENT_STYLE : INACTIVE_SEGMENT_STYLE}
          >
            Σημασιολογική
          </button>
        </div>
      </div>

      {mode === 'structured' ? (
        <div className="flex flex-col gap-3.5">
          <label className="flex flex-col gap-1.5">
            <span className={LABEL_CLASS}>Λειτουργία</span>
            <select
              aria-label="Λειτουργία"
              value={operation}
              onChange={(e) => handleOperationChange(e.target.value as StructuredOperation)}
              className={SELECT_CLASS}
              style={selectStyle(operation)}
            >
              {OPERATIONS.map((op) => (
                <option key={op.value} value={op.value}>
                  {op.label}
                </option>
              ))}
            </select>
          </label>

          {operation === 'top_bottom_sections' && (
            <label className="flex flex-col gap-1.5">
              <span className={LABEL_CLASS}>Αριθμός ενοτήτων (n)</span>
              <input
                aria-label="Αριθμός ενοτήτων"
                type="number"
                min={1}
                value={n}
                onChange={(e) => setN(e.target.value)}
                className={FIELD_CLASS}
                style={fieldStyle}
              />
            </label>
          )}
        </div>
      ) : (
        <label className="flex flex-col gap-1.5">
          <span className={LABEL_CLASS}>Ερώτηση</span>
          <textarea
            aria-label="Ερώτηση"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={3}
            className={FIELD_CLASS}
            style={{ ...fieldStyle, minHeight: '80px' }}
          />
          {questionTooShort && question.length > 0 && (
            <span className="font-mono text-[11px]" style={{ color: '#ff6b6b' }}>
              Η ερώτηση απαιτεί τουλάχιστον 3 χαρακτήρες
            </span>
          )}
        </label>
      )}

      {formError && (
        <p className="text-sm" style={{ color: '#ff6b6b' }}>
          {formError}
        </p>
      )}

      {loading && mode === 'semantic' && (
        <p className="text-[11px]" style={{ color: '#8b8b95' }}>
          Το τοπικό μοντέλο επεξεργάζεται το ερώτημα — μπορεί να πάρει έως 3-4 λεπτά.
        </p>
      )}

      <button
        type="submit"
        disabled={!canSubmit || loading}
        className="mt-auto flex w-full items-center justify-center gap-2 rounded-lg py-3 text-[13px] font-semibold disabled:cursor-not-allowed disabled:opacity-50"
        style={{ backgroundColor: '#f2ede0', color: '#0a0a0c' }}
      >
        {loading && (
          <svg
            className="animate-spin"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden
          >
            <circle cx="12" cy="12" r="10" stroke="#0a0a0c" strokeWidth="3" opacity="0.25" />
            <path d="M22 12a10 10 0 0 0-10-10" stroke="#0a0a0c" strokeWidth="3" strokeLinecap="round" />
          </svg>
        )}
        {loading ? 'Αποστολή...' : 'Υποβολή ερωτήματος ⏎'}
      </button>

      <div className="flex flex-col gap-1">
        <p className="text-left font-mono text-[9px]" style={{ color: '#5a5a63' }}>
          ΔΙΠΛΗΚΥΒ-Τμήματα Τεχνητής Νοημοσύνης & Αναλυτικής Δεδομένων
        </p>
        <p className="text-left font-mono text-[9px]" style={{ color: '#5a5a63' }}>
          v1.0 · 2026
        </p>
      </div>
    </form>
  )
}
