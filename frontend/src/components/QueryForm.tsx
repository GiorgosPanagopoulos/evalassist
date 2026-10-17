import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react'
import type { ApiClient, ApiError } from '../api/client'
import type {
  PersonOut,
  SemanticResult,
  StructuredOperation,
  StructuredResult,
} from '../api/types'
import { CHEVRON_BG } from '../lib/styles'
import type { QueryMode } from './ModeBadge'
import { PersonCombobox } from './PersonCombobox'

// Structural subset so tests can pass a plain Fake* object instead of a
// real ApiClient instance (same fake-injection philosophy as the backend tests).
export type QueryFormApi = Pick<
  ApiClient,
  'getPersons' | 'getPeriods' | 'queryStructured' | 'querySemantic'
>

// 'timeline' is a UI operation: it reloads the timeline, it is not a
// structured query.
type Operation = StructuredOperation | 'timeline'

interface QueryFormProps {
  api: QueryFormApi
  // personId: το άτομο ΤΟΥ ΑΙΤΗΜΑΤΟΣ, ώστε ο γονέας να απορρίπτει απάντηση που
  // φτάνει αφού ο χρήστης έχει ήδη αλλάξει άτομο.
  onResult: (result: StructuredResult | SemanticResult, auditId: number, personId: string) => void
  onError?: (error: ApiError) => void
  onModeChange?: (mode: QueryMode) => void
  onTimelineRequest?: () => void
  // features.semantic_enabled από το /api/auth/me. Ο server απαντά έτσι κι
  // αλλιώς 403 όταν είναι κλειστό· εδώ απλώς δεν προσφέρεται η επιλογή.
  semanticEnabled?: boolean
  // Controlled επιλογή ατόμου (μία πηγή αλήθειας στο App). Χωρίς personId το
  // component κρατά δικό του state (π.χ. μεμονωμένα tests).
  personId?: string
  onPersonChange?: (person: PersonOut | null) => void
  trailing?: ReactNode
}

export const SEMANTIC_DISABLED_TEXT = 'Η σημασιολογική αναζήτηση δεν είναι ενεργή σε αυτή την εγκατάσταση.'

const OPERATIONS: { value: Operation; label: string }[] = [
  { value: 'timeline', label: 'Χρονογραμμή βαθμολογίας' },
  { value: 'get_scores', label: 'Βαθμολογίες' },
  { value: 'compare_periods', label: 'Σύγκριση περιόδων' },
  { value: 'top_bottom_sections', label: 'Κορυφαίες / χαμηλότερες ενότητες' },
  { value: 'get_promotions_table', label: 'Κρίσεις προαγωγών' },
  { value: 'get_service_time_table', label: 'Συνολικός χρόνος υπηρεσίας' },
]

// Career-wide: το backend αγνοεί το period και διαβάζει πάντα CAREER_PERIOD
// (CAREER_WIDE_OPERATIONS στο backend/app/api/routes_query.py). Το period
// είναι υποχρεωτικό στο request, οπότε στέλνεται η ίδια η σύμβαση 'career'.
const CAREER_WIDE_OPERATIONS: readonly Operation[] = [
  'get_promotions_table',
  'get_service_time_table',
]
export const CAREER_PERIOD = 'career'
export const CAREER_WIDE_TEXT = 'Αφορά όλη τη σταδιοδρομία'

const CONTROL = 'h-11 rounded-lg border border-line-strong bg-input text-[14px] text-ink'
const SELECT_CLASS = `${CONTROL} appearance-none bg-no-repeat bg-[right_12px_center] pl-3 pr-9 disabled:cursor-not-allowed disabled:opacity-50`
const SEGMENT = 'h-full flex-1 px-3.5 text-[14px] font-semibold disabled:cursor-not-allowed disabled:opacity-40'

function PeriodSelect({
  label,
  value,
  onChange,
  options,
  disabled,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: string[]
  disabled: boolean
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className={`${SELECT_CLASS} min-w-0 flex-[1_1_160px] sm:flex-[0_1_220px] ${value ? 'font-mono text-[13px]' : 'text-muted'}`}
      style={CHEVRON_BG}
    >
      <option value="">{label === 'Περίοδος' ? 'Επιλέξτε περίοδο' : `${label}: περίοδος`}</option>
      {options.map((p) => (
        <option key={p} value={p}>
          {p}
        </option>
      ))}
    </select>
  )
}

export function QueryForm({
  api,
  onResult,
  onError,
  onModeChange,
  onTimelineRequest,
  semanticEnabled = true,
  personId: controlledPersonId,
  onPersonChange,
  trailing,
}: QueryFormProps) {
  const [persons, setPersons] = useState<PersonOut[]>([])
  const [periods, setPeriods] = useState<string[]>([])
  const [ownPersonId, setOwnPersonId] = useState('')
  const personId = controlledPersonId ?? ownPersonId
  const [period, setPeriod] = useState('')
  const [mode, setMode] = useState<QueryMode>('structured')
  const [operation, setOperation] = useState<Operation>('get_scores')
  const [otherPeriod, setOtherPeriod] = useState('')
  const [n, setN] = useState('')
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    onModeChange?.(mode)
  }, [mode, onModeChange])

  useEffect(() => {
    if (!semanticEnabled) setMode('structured')
  }, [semanticEnabled])

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

  const structured = mode === 'structured'
  const isTimeline = structured && operation === 'timeline'
  const careerWide = structured && CAREER_WIDE_OPERATIONS.includes(operation)
  const isCompare = structured && operation === 'compare_periods'
  const needsPeriod = !isTimeline && !careerWide
  const questionTooShort = mode === 'semantic' && question.trim().length < 3
  const compareMissingOtherPeriod = isCompare && !otherPeriod

  const canSubmit =
    Boolean(personId) && (!needsPeriod || Boolean(period)) && !questionTooShort && !compareMissingOtherPeriod

  function handlePersonChange(nextId: string) {
    setOwnPersonId(nextId)
    onPersonChange?.(persons.find((p) => p.person_id === nextId) ?? null)
  }

  function handleOperationChange(next: Operation) {
    setOperation(next)
    setOtherPeriod('')
    setN('')
  }

  async function handleSubmit(e: SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!canSubmit || loading) return
    if (isTimeline) {
      setFormError(null)
      onTimelineRequest?.()
      return
    }
    setLoading(true)
    setFormError(null)
    try {
      if (structured) {
        const op = operation as StructuredOperation
        const response = await api.queryStructured({
          person_id: personId,
          period: careerWide ? CAREER_PERIOD : period,
          operation: op,
          ...(op === 'compare_periods' ? { other_period: otherPeriod } : {}),
          ...(op === 'top_bottom_sections' && n ? { n: Number(n) } : {}),
        })
        onResult(response.result, response.audit_id, personId)
      } else {
        const response = await api.querySemantic({
          person_id: personId,
          period,
          question: question.trim(),
        })
        onResult(response.result, response.audit_id, personId)
      }
    } catch (err) {
      const apiError = err as ApiError
      setFormError(apiError.detail ?? 'Σφάλμα')
      onError?.(apiError)
    } finally {
      setLoading(false)
    }
  }

  const showSecondRow =
    mode === 'semantic' ||
    careerWide ||
    (structured && operation === 'top_bottom_sections') ||
    !semanticEnabled ||
    Boolean(formError)

  return (
    <form onSubmit={handleSubmit} aria-label="Ερώτημα" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <PersonCombobox persons={persons} value={personId} onChange={handlePersonChange} />

        <div
          className="flex h-11 flex-[1_1_100%] overflow-hidden rounded-lg bg-input ring-1 ring-line-strong sm:flex-none"
          role="group"
          aria-label="Τύπος ερωτήματος"
        >
          <button
            type="button"
            onClick={() => setMode('structured')}
            aria-pressed={structured}
            className={`${SEGMENT} ${structured ? 'bg-navy text-ink' : 'text-muted'}`}
          >
            Δομημένη
          </button>
          <button
            type="button"
            onClick={() => setMode('semantic')}
            aria-pressed={mode === 'semantic'}
            disabled={!semanticEnabled}
            title={semanticEnabled ? undefined : SEMANTIC_DISABLED_TEXT}
            aria-describedby={semanticEnabled ? undefined : 'semantic-disabled-note'}
            className={`${SEGMENT} ${mode === 'semantic' ? 'bg-navy text-ink' : 'text-muted'}`}
          >
            Σημασιολογική
          </button>
        </div>

        {structured && (
          <select
            aria-label="Λειτουργία"
            value={operation}
            onChange={(e) => handleOperationChange(e.target.value as Operation)}
            className={`${SELECT_CLASS} min-w-0 flex-[1_1_100%] sm:flex-[0_1_260px]`}
            style={CHEVRON_BG}
          >
            {OPERATIONS.map((op) => (
              <option key={op.value} value={op.value}>
                {op.label}
              </option>
            ))}
          </select>
        )}

        {isCompare ? (
          <>
            <PeriodSelect label="Από" value={period} onChange={setPeriod} options={periods} disabled={!personId} />
            <PeriodSelect
              label="Έως"
              value={otherPeriod}
              onChange={setOtherPeriod}
              options={periods.filter((p) => p !== period)}
              disabled={!personId}
            />
          </>
        ) : (
          needsPeriod && (
            <PeriodSelect label="Περίοδος" value={period} onChange={setPeriod} options={periods} disabled={!personId} />
          )
        )}

        <button
          type="submit"
          aria-label="Υποβολή ερωτήματος"
          disabled={!canSubmit || loading}
          className="flex h-11 shrink-0 items-center justify-center gap-2 rounded-lg bg-gold px-6 text-[14px] font-semibold text-bg hover:bg-gold-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading && (
            <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
              <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </svg>
          )}
          {loading ? 'Αποστολή...' : 'Υποβολή'}
        </button>

        {trailing && <div className="ml-auto flex shrink-0 items-center">{trailing}</div>}
      </div>

      {showSecondRow && (
        <div className="flex flex-col gap-2">
          {careerWide && (
            <p data-testid="career-wide-note" className="text-[13px] text-muted">
              <span className="text-subtle">Περίοδος:</span> {CAREER_WIDE_TEXT}
            </p>
          )}

          {structured && operation === 'top_bottom_sections' && (
            <label className="flex items-center gap-2 text-[13px] text-muted">
              Αριθμός ενοτήτων (n)
              <input
                aria-label="Αριθμός ενοτήτων"
                type="number"
                min={1}
                value={n}
                onChange={(e) => setN(e.target.value)}
                className={`${CONTROL} w-24 px-3`}
              />
            </label>
          )}

          {mode === 'semantic' && (
            <label className="flex flex-col gap-1.5">
              <span className="text-[12px] font-semibold tracking-[.06em] text-muted uppercase">Ερώτηση</span>
              <textarea
                aria-label="Ερώτηση"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                rows={2}
                className="min-h-[64px] rounded-lg border border-line-strong bg-input px-3 py-2.5 text-[14px] text-ink"
              />
              {questionTooShort && question.length > 0 && (
                <span className="font-mono text-[12px] text-danger-soft">
                  Η ερώτηση απαιτεί τουλάχιστον 3 χαρακτήρες
                </span>
              )}
            </label>
          )}

          {!semanticEnabled && (
            <p id="semantic-disabled-note" className="text-[12px] text-subtle">
              {SEMANTIC_DISABLED_TEXT}
            </p>
          )}

          {formError && <p className="text-[13px] text-danger-soft">{formError}</p>}

          {loading && mode === 'semantic' && (
            <p className="text-[12px] text-muted">
              Το τοπικό μοντέλο επεξεργάζεται το ερώτημα, μπορεί να πάρει έως 3-4 λεπτά.
            </p>
          )}
        </div>
      )}
    </form>
  )
}
