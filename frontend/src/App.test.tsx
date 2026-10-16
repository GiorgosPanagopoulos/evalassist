import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { ApiClient } from './api/client'
import type { Me } from './api/types'
import { SEMANTIC_DISABLED_TEXT } from './components/QueryForm'

// Ψεύτικο backend: "METHOD path" -> [status, body] ή συνάρτηση που τα
// επιστρέφει. Ο πραγματικός ApiClient τρέχει από πάνω, ώστε να ελέγχεται και
// η ροή 401 -> login. Μόνο συνθετικά δεδομένα.
type Reply = [number, unknown]
type Routes = Record<string, Reply | ((init?: RequestInit) => Reply | Promise<Reply>)>

const FEATURES = { semantic_enabled: true }
const USER: Me = { id: 2, username: 'alice', role: 'user', must_change_pw: false, features: FEATURES }
const ADMIN: Me = { id: 1, username: 'root', role: 'admin', must_change_pw: false, features: FEATURES }
const PERSONS = [{ person_id: 'p1', name: 'Συνθετικός Α' }]

function makeApi(routes: Routes) {
  const fetchFn = vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${url}`
    const route = routes[key]
    if (!route) throw new Error(`unexpected request: ${key}`)
    const [status, body] = typeof route === 'function' ? await route(init) : route
    if (status === 204) return new Response(null, { status })
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  })
  return { api: new ApiClient(undefined, fetchFn as unknown as typeof fetch), fetchFn }
}

const COMMON: Routes = {
  'GET api/health': [200, { status: 'ok', ollama_reachable: true }],
  'GET api/persons': [200, PERSONS],
}

describe('App auth flow', () => {
  it('shows the login page when there is no session, then the app after login', async () => {
    const { api, fetchFn } = makeApi({
      ...COMMON,
      'GET api/auth/me': [401, { detail: 'Απαιτείται σύνδεση.' }],
      'POST api/auth/login': [200, USER],
    })
    const user = userEvent.setup()
    render(<App api={api} />)

    await user.type(await screen.findByLabelText('Όνομα χρήστη'), 'alice')
    await user.type(screen.getByLabelText('Κωδικός'), 'synthetic-pass-0001')
    await user.click(screen.getByRole('button', { name: 'Σύνδεση' }))

    expect(await screen.findByRole('button', { name: 'Αποσύνδεση' })).toBeInTheDocument()
    expect(screen.getByLabelText('Συνδεδεμένος χρήστης')).toHaveTextContent('alice')
    // Κανένα αίτημα δεδομένων πριν από το login.
    const firstLogin = fetchFn.mock.calls.findIndex(([url]) => url === 'api/auth/login')
    const firstData = fetchFn.mock.calls.findIndex(([url]) => url === 'api/persons')
    expect(firstData).toBeGreaterThan(firstLogin)
  })

  it('shows the backend error on wrong credentials and stays on the login page', async () => {
    const { api } = makeApi({
      'GET api/auth/me': [401, { detail: 'Απαιτείται σύνδεση.' }],
      'POST api/auth/login': [401, { detail: 'Λάθος όνομα χρήστη ή κωδικός.' }],
    })
    const user = userEvent.setup()
    render(<App api={api} />)

    await user.type(await screen.findByLabelText('Όνομα χρήστη'), 'alice')
    await user.type(screen.getByLabelText('Κωδικός'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: 'Σύνδεση' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Λάθος όνομα χρήστη ή κωδικός.')
    expect(screen.getByLabelText('Κωδικός')).toHaveValue('')
  })

  it('a 401 while using the app (expired session) goes back to the login page', async () => {
    const { api } = makeApi({
      ...COMMON,
      'GET api/auth/me': [200, USER],
      'GET api/persons/p1/periods': [200, ['2025-01-01..2025-12-31']],
      'GET api/person/p1/timeline': [401, { detail: 'Απαιτείται σύνδεση.' }],
    })
    const user = userEvent.setup()
    render(<App api={api} />)

    await screen.findByRole('option', { name: /Συνθετικός Α/ })
    await user.selectOptions(screen.getByLabelText('Άτομο'), 'p1')

    expect(await screen.findByRole('form', { name: 'Σύνδεση' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Αποσύνδεση' })).not.toBeInTheDocument()
  })

  it('must_change_pw shows only the change-password page, then the app after the change', async () => {
    const { api, fetchFn } = makeApi({
      ...COMMON,
      'GET api/auth/me': [200, { ...USER, must_change_pw: true }],
      'POST api/auth/change-password': [204, null],
    })
    const user = userEvent.setup()
    render(<App api={api} />)

    expect(await screen.findByRole('form', { name: 'Αλλαγή κωδικού' })).toBeInTheDocument()
    expect(screen.getByText('Πρέπει να αλλάξετε τον προσωρινό κωδικό πριν συνεχίσετε.')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Χρονογραμμή βαθμολογίας' })).not.toBeInTheDocument()
    expect(fetchFn.mock.calls.some(([url]) => url === 'api/persons')).toBe(false)

    await user.type(screen.getByLabelText('Τρέχων κωδικός'), 'temp-password-x')
    await user.type(screen.getByLabelText('Νέος κωδικός'), 'short')
    await user.type(screen.getByLabelText('Επανάληψη νέου κωδικού'), 'short')
    await user.click(screen.getByRole('button', { name: 'Αλλαγή κωδικού' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('τουλάχιστον 12')

    await user.clear(screen.getByLabelText('Νέος κωδικός'))
    await user.clear(screen.getByLabelText('Επανάληψη νέου κωδικού'))
    await user.type(screen.getByLabelText('Νέος κωδικός'), 'a-new-synthetic-pass')
    await user.type(screen.getByLabelText('Επανάληψη νέου κωδικού'), 'a-new-synthetic-pass')
    await user.click(screen.getByRole('button', { name: 'Αλλαγή κωδικού' }))

    expect(await screen.findByRole('region', { name: 'Χρονογραμμή βαθμολογίας' })).toBeInTheDocument()
    const changeCall = fetchFn.mock.calls.find(([url]) => url === 'api/auth/change-password')
    expect(JSON.parse(changeCall?.[1]?.body as string)).toEqual({
      current_password: 'temp-password-x',
      new_password: 'a-new-synthetic-pass',
    })
  })

  it('user management is not shown to a plain user', async () => {
    const { api } = makeApi({ ...COMMON, 'GET api/auth/me': [200, USER] })
    render(<App api={api} />)

    expect(await screen.findByRole('button', { name: 'Αποσύνδεση' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Χρήστες' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Διαχείριση χρηστών' })).not.toBeInTheDocument()
  })

  it('an admin can open user management', async () => {
    const { api } = makeApi({
      ...COMMON,
      'GET api/auth/me': [200, ADMIN],
      'GET api/admin/users': [
        200,
        [{ id: 1, username: 'root', role: 'admin', is_active: true, must_change_pw: false, locked: false, created_at: '' }],
      ],
    })
    const user = userEvent.setup()
    render(<App api={api} />)

    await user.click(await screen.findByRole('button', { name: 'Χρήστες' }))

    expect(await screen.findByRole('region', { name: 'Διαχείριση χρηστών' })).toBeInTheDocument()
    expect(await screen.findByRole('cell', { name: 'root' })).toBeInTheDocument()
  })

  it('logout calls the API and returns to the login page', async () => {
    const { api, fetchFn } = makeApi({
      ...COMMON,
      'GET api/auth/me': [200, USER],
      'POST api/auth/logout': [204, null],
    })
    const user = userEvent.setup()
    render(<App api={api} />)

    await user.click(await screen.findByRole('button', { name: 'Αποσύνδεση' }))

    expect(await screen.findByRole('form', { name: 'Σύνδεση' })).toBeInTheDocument()
    expect(fetchFn.mock.calls.some(([url, init]) => url === 'api/auth/logout' && init?.method === 'POST')).toBe(true)
  })

  it('features.semantic_enabled=false from /me disables the Σημασιολογική option with an explanation', async () => {
    const { api } = makeApi({
      ...COMMON,
      'GET api/auth/me': [200, { ...USER, features: { semantic_enabled: false } }],
    })
    render(<App api={api} />)

    const semantic = await screen.findByRole('button', { name: 'Σημασιολογική' })
    expect(semantic).toBeDisabled()
    expect(semantic).toHaveAccessibleDescription(SEMANTIC_DISABLED_TEXT)
    expect(screen.getByRole('button', { name: 'Δομημένη' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('features.semantic_enabled=true from /me leaves the Σημασιολογική option enabled', async () => {
    const { api } = makeApi({ ...COMMON, 'GET api/auth/me': [200, USER] })
    render(<App api={api} />)

    expect(await screen.findByRole('button', { name: 'Σημασιολογική' })).toBeEnabled()
    expect(screen.queryByText(SEMANTIC_DISABLED_TEXT)).not.toBeInTheDocument()
  })
})


// --- μία επιλογή ατόμου: αριστερό πάνελ -> χρονογραμμή + αποτελέσματα ----------

const TWO_PERSONS = [
  { person_id: 'p1', name: 'Συνθετικός Α' },
  { person_id: 'p2', name: 'Συνθετικός Β' },
]
const PERIOD_OF: Record<string, string> = { p1: '2012-01-01..2012-12-31', p2: '2013-01-01..2013-12-31' }
const DOC_OF: Record<string, string> = { p1: 'doc-of-A', p2: 'doc-of-B' }

function timelineReply(personId: string): Reply {
  return [
    200,
    {
      result: {
        person_id: personId,
        points: [
          {
            period: PERIOD_OF[personId],
            period_start: PERIOD_OF[personId].slice(0, 10),
            kind: 'Ε.Α.',
            score: 90,
            doc_id: DOC_OF[personId],
            page: 7,
            section: 'ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ',
          },
        ],
        retrieved_doc_ids: [DOC_OF[personId]],
      },
      audit_id: 100,
    },
  ]
}

function structuredReply(init?: RequestInit): Reply {
  const personId = JSON.parse(init?.body as string).person_id as string
  return [
    200,
    {
      result: {
        mode: 'structured',
        data: { person_id: personId, period: PERIOD_OF[personId], ea_type: 'Ε.Α.', score: 90 },
        citations: [{ doc_id: DOC_OF[personId], page: 7, section: 'ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ - ΧΑΡΑΚΤΗΡΙΣΜΟΣ' }],
        retrieved_doc_ids: [DOC_OF[personId]],
      },
      audit_id: 200,
    },
  ]
}

function personRoutes(overrides: Routes = {}): Routes {
  return {
    'GET api/health': [200, { status: 'ok', ollama_reachable: true }],
    'GET api/auth/me': [200, USER],
    'GET api/persons': [200, TWO_PERSONS],
    'GET api/persons/p1/periods': [200, [PERIOD_OF.p1]],
    'GET api/persons/p2/periods': [200, [PERIOD_OF.p2]],
    'GET api/person/p1/timeline': () => timelineReply('p1'),
    'GET api/person/p2/timeline': () => timelineReply('p2'),
    'POST api/query/structured': structuredReply,
    ...overrides,
  }
}

async function choosePerson(user: ReturnType<typeof userEvent.setup>, personId: string) {
  await screen.findByRole('option', { name: /Συνθετικός Α/ })
  await user.selectOptions(screen.getByLabelText('Άτομο'), personId)
}

async function submitScores(user: ReturnType<typeof userEvent.setup>, personId: string) {
  await screen.findByRole('option', { name: PERIOD_OF[personId] })
  await user.selectOptions(screen.getByLabelText('Περίοδος'), PERIOD_OF[personId])
  await user.click(screen.getByRole('button', { name: /Υποβολή ερωτήματος/ }))
}

describe('single person selection', () => {
  it('the timeline loads for the person chosen on the left, with an explicit heading', async () => {
    const { api, fetchFn } = makeApi(personRoutes())
    const user = userEvent.setup()
    render(<App api={api} />)

    const timeline = await screen.findByRole('region', { name: 'Χρονογραμμή βαθμολογίας' })
    expect(within(timeline).getByText('Επιλέξτε άτομο από αριστερά')).toBeInTheDocument()

    await choosePerson(user, 'p1')

    expect(await within(timeline).findByText(/έγγραφα: doc-of-A/)).toBeInTheDocument()
    expect(screen.getByTestId('timeline-person')).toHaveTextContent('Άτομο: Συνθετικός Α (p1)')
    const timelineCalls = fetchFn.mock.calls.filter(([url]) => String(url).includes('/timeline'))
    expect(timelineCalls.map(([url]) => url)).toEqual(['api/person/p1/timeline'])
  })

  it('has exactly one person dropdown in the DOM', async () => {
    const { api } = makeApi(personRoutes())
    render(<App api={api} />)

    await screen.findByRole('option', { name: /Συνθετικός Α/ })
    const personSelects = screen
      .getAllByRole('combobox')
      .filter((el) => within(el).queryByRole('option', { name: /Συνθετικός Α/ }))
    expect(personSelects).toHaveLength(1)
    expect(personSelects[0]).toHaveAccessibleName('Άτομο')
    expect(screen.queryByLabelText('Άτομο χρονογραμμής')).not.toBeInTheDocument()
  })

  it('switching A -> B clears A results; the screen never shows two persons', async () => {
    const { api } = makeApi(personRoutes())
    const user = userEvent.setup()
    render(<App api={api} />)

    await choosePerson(user, 'p1')
    await submitScores(user, 'p1')
    expect(await screen.findByTestId('results-person')).toHaveTextContent('Άτομο: Συνθετικός Α (p1)')
    expect(screen.getByTestId('citations')).toHaveTextContent('doc-of-A')

    await user.selectOptions(screen.getByLabelText('Άτομο'), 'p2')

    expect(screen.queryByTestId('results-person')).not.toBeInTheDocument()
    expect(screen.queryByTestId('citations')).not.toBeInTheDocument()
    expect(await screen.findByText(/έγγραφα: doc-of-B/)).toBeInTheDocument()
    expect(screen.getByTestId('timeline-person')).toHaveTextContent('Άτομο: Συνθετικός Β (p2)')
    expect(screen.queryByText(/doc-of-A/)).not.toBeInTheDocument()
    expect(document.body.textContent).not.toContain('doc-of-A')

    await submitScores(user, 'p2')
    expect(await screen.findByTestId('results-person')).toHaveTextContent('Άτομο: Συνθετικός Β (p2)')
    for (const id of ['results-person', 'timeline-person']) {
      expect(screen.getByTestId(id)).not.toHaveTextContent('p1')
    }
    expect(screen.getByTestId('citations')).toHaveTextContent('doc-of-B')
    expect(document.body.textContent).not.toContain('doc-of-A')
  })

  it('drops a result for A that arrives after switching to B', async () => {
    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    const { api, fetchFn } = makeApi(
      personRoutes({
        'POST api/query/structured': async (init) => {
          await gate
          return structuredReply(init)
        },
      }),
    )
    const user = userEvent.setup()
    render(<App api={api} />)

    await choosePerson(user, 'p1')
    await submitScores(user, 'p1')
    await waitFor(() =>
      expect(fetchFn.mock.calls.some(([url]) => url === 'api/query/structured')).toBe(true),
    )

    await user.selectOptions(screen.getByLabelText('Άτομο'), 'p2')
    expect(await screen.findByText(/έγγραφα: doc-of-B/)).toBeInTheDocument()
    release()
    // Η απάντηση του Α ολοκληρώνεται (το κουμπί ξαναενεργοποιείται) αλλά δεν εμφανίζεται.
    await waitFor(() => expect(screen.getByRole('button', { name: /Υποβολή ερωτήματος/ })).toHaveTextContent('Υποβολή'))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(screen.queryByTestId('results-person')).not.toBeInTheDocument()
    expect(document.body.textContent).not.toContain('doc-of-A')
    expect(screen.getByTestId('timeline-person')).toHaveTextContent('Άτομο: Συνθετικός Β (p2)')
  })
})
