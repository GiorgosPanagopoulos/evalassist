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

async function openUserMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: 'Μενού χρήστη' }))
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

    await openUserMenu(user)
    expect(screen.getByRole('menuitem', { name: 'Αποσύνδεση' })).toBeInTheDocument()
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

    await user.click(await screen.findByRole('combobox', { name: 'Άτομο' }))
    await user.click(await screen.findByRole('option', { name: /Συνθετικός Α/ }))

    expect(await screen.findByRole('form', { name: 'Σύνδεση' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Μενού χρήστη' })).not.toBeInTheDocument()
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
    const user = userEvent.setup()
    render(<App api={api} />)

    await openUserMenu(user)
    expect(screen.getByRole('menuitem', { name: 'Αποσύνδεση' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Χρήστες' })).not.toBeInTheDocument()
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

    await openUserMenu(user)
    await user.click(screen.getByRole('menuitem', { name: 'Χρήστες' }))

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

    await openUserMenu(user)
    await user.click(screen.getByRole('menuitem', { name: 'Αποσύνδεση' }))

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
  await user.click(await screen.findByRole('combobox', { name: 'Άτομο' }))
  const listbox = screen.getByRole('listbox', { name: 'Άτομα' })
  await user.click(await within(listbox).findByRole('option', { name: new RegExp(`\\(${personId}\\)$`) }))
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
    expect(within(timeline).getByText('Επιλέξτε άτομο από την αναζήτηση')).toBeInTheDocument()

    await choosePerson(user, 'p1')

    expect(await within(timeline).findByText(/έγγραφα: doc-of-A/)).toBeInTheDocument()
    expect(screen.getByTestId('timeline-person')).toHaveTextContent('Άτομο: Συνθετικός Α (p1)')
    const timelineCalls = fetchFn.mock.calls.filter(([url]) => String(url).includes('/timeline'))
    expect(timelineCalls.map(([url]) => url)).toEqual(['api/person/p1/timeline'])
  })

  it('has exactly one person dropdown in the DOM', async () => {
    const { api } = makeApi(personRoutes())
    const user = userEvent.setup()
    render(<App api={api} />)

    await user.click(await screen.findByRole('combobox', { name: 'Άτομο' }))
    const personOptions = await screen.findAllByRole('option', { name: /Συνθετικός Α/ })
    expect(personOptions).toHaveLength(1)
    const listboxId = personOptions[0].closest('[role="listbox"]')?.id
    const personSelects = screen
      .getAllByRole('combobox')
      .filter((el) => listboxId && el.getAttribute('aria-controls') === listboxId)
    expect(personSelects).toHaveLength(1)
    expect(personSelects[0]).toHaveAccessibleName('Άτομο')
    expect(screen.queryByLabelText('Άτομο χρονογραμμής')).not.toBeInTheDocument()
  })

  it('typing in the person search fetches nothing person-scoped until an option is chosen', async () => {
    const { api, fetchFn } = makeApi(personRoutes())
    const user = userEvent.setup()
    render(<App api={api} />)

    const combobox = await screen.findByRole('combobox', { name: 'Άτομο' })
    await user.click(combobox)
    await user.type(combobox, 'Συνθετικός')
    const listbox = screen.getByRole('listbox', { name: 'Άτομα' })
    expect(await within(listbox).findAllByRole('option')).toHaveLength(2)
    await user.type(combobox, ' Β')
    expect(within(listbox).getAllByRole('option')).toHaveLength(1)

    const personScoped = () =>
      fetchFn.mock.calls.map(([url]) => String(url)).filter((url) => /\/(timeline|periods)$/.test(url))
    expect(personScoped()).toEqual([])
    expect(screen.queryByTestId('timeline-person')).not.toBeInTheDocument()

    await user.click(within(listbox).getByRole('option', { name: /\(p2\)$/ }))

    await waitFor(() => expect(personScoped()).toContain('api/person/p2/timeline'))
    expect(personScoped().some((url) => url.includes('p1'))).toBe(false)
  })

  it('switching A -> B clears A results; the screen never shows two persons', async () => {
    const { api } = makeApi(personRoutes())
    const user = userEvent.setup()
    render(<App api={api} />)

    await choosePerson(user, 'p1')
    await submitScores(user, 'p1')
    expect(await screen.findByTestId('results-person')).toHaveTextContent('Άτομο: Συνθετικός Α (p1)')
    expect(screen.getByTestId('citations')).toHaveTextContent('doc-of-A')

    await choosePerson(user, 'p2')

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

    await choosePerson(user, 'p2')
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

// --- feature flags: actions without a backend stay hidden ---------------------

describe('feature flags', () => {
  async function loadTimeline(features: Me['features']) {
    const { api } = makeApi(personRoutes({ 'GET api/auth/me': [200, { ...USER, features }] }))
    const user = userEvent.setup()
    render(<App api={api} />)
    await choosePerson(user, 'p1')
    await screen.findByRole('list', { name: 'Λίστα περιόδων' })
    return user
  }

  it('absent flags hide PDF, review flag, export, history and flags in the rail', async () => {
    await loadTimeline({ semantic_enabled: true })

    expect(screen.queryByRole('link', { name: /Άνοιγμα PDF/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Σήμανση για έλεγχο/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'CSV' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'PDF' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ιστορικό ελέγχου' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Σημάνσεις' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Αντιγραφή παραπομπής' })).toBeEnabled()
  })

  it('document_file_enabled opens the selected period at its page', async () => {
    await loadTimeline({ semantic_enabled: true, document_file_enabled: true, export_enabled: true })

    const open = screen.getByRole('link', { name: 'Άνοιγμα PDF στη σελίδα 7' })
    expect(open).toHaveAttribute(
      'href',
      `api/person/p1/documents/doc-of-A/file?period=${encodeURIComponent(PERIOD_OF.p1)}#page=7`,
    )
    expect(screen.getByRole('button', { name: 'CSV' })).toBeInTheDocument()
  })
})

describe('timeline workspace', () => {
  it('shows the person card, the mode badge and the footer, never the doc hash in the card', async () => {
    const { api } = makeApi(personRoutes())
    const user = userEvent.setup()
    render(<App api={api} />)
    await choosePerson(user, 'p1')

    const card = await screen.findByTestId('timeline-person')
    expect(card.closest('div.rounded-2xl')?.textContent).not.toContain('doc-of-A')
    expect(screen.getByTestId('mode-badge')).toHaveTextContent('Ντετερμινιστικό · χωρίς LLM')
    expect(screen.getByTestId('status-footer')).toHaveTextContent('audit #100')
    expect(screen.getByTestId('status-footer')).toHaveTextContent('GET /api/person/{person_id}/timeline')

    await user.click(screen.getByRole('button', { name: 'Σημασιολογική' }))
    expect(screen.getByTestId('mode-badge')).toHaveTextContent('LLM · επαλήθευσε τις πηγές')
  })

  it('selecting a period in the list selects it in the chart and shows its citation', async () => {
    const { api } = makeApi(personRoutes())
    const user = userEvent.setup()
    render(<App api={api} />)
    await choosePerson(user, 'p1')

    const row = await screen.findByRole('button', { name: /Ε\.Α\., βαθμός 90/ })
    expect(row).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('ea-point')).toHaveAttribute('data-selected', 'true')
    expect(screen.getByTestId('selected-citation')).toHaveTextContent('doc-of-A · σελ. 7 · ΣΥΝΟΛΙΚΗ ΕΜΦΑΝΙΣΗ')
  })

  it('no "submit a query" prompt is shown once a person is chosen', async () => {
    const { api } = makeApi(personRoutes())
    const user = userEvent.setup()
    render(<App api={api} />)
    await choosePerson(user, 'p1')
    await submitScores(user, 'p1')

    expect(await screen.findByTestId('results-person')).toBeInTheDocument()
    expect(screen.queryByText(/Υποβάλετε ένα ερώτημα/)).not.toBeInTheDocument()
  })
})

describe('avatar', () => {
  it('uses the Greek display name initials when /me sends one, else the username', async () => {
    const { api } = makeApi({ ...COMMON, 'GET api/auth/me': [200, { ...USER, display_name: 'Γεώργιος Παναγόπουλος' }] })
    const { unmount } = render(<App api={api} />)
    expect(await screen.findByRole('button', { name: 'Μενού χρήστη' })).toHaveTextContent('ΓΠ')
    unmount()

    const { api: plain } = makeApi({ ...COMMON, 'GET api/auth/me': [200, USER] })
    render(<App api={plain} />)
    expect(await screen.findByRole('button', { name: 'Μενού χρήστη' })).toHaveTextContent('AL')
  })
})
