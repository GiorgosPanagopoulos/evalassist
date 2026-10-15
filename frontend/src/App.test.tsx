import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { ApiClient } from './api/client'
import type { Me } from './api/types'

// Ψεύτικο backend: "METHOD path" -> [status, body] ή συνάρτηση που τα
// επιστρέφει. Ο πραγματικός ApiClient τρέχει από πάνω, ώστε να ελέγχεται και
// η ροή 401 -> login. Μόνο συνθετικά δεδομένα.
type Reply = [number, unknown]
type Routes = Record<string, Reply | (() => Reply)>

const USER: Me = { id: 2, username: 'alice', role: 'user', must_change_pw: false }
const ADMIN: Me = { id: 1, username: 'root', role: 'admin', must_change_pw: false }
const PERSONS = [{ person_id: 'p1', name: 'Συνθετικός Α' }]

function makeApi(routes: Routes) {
  const fetchFn = vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${url}`
    const route = routes[key]
    if (!route) throw new Error(`unexpected request: ${key}`)
    const [status, body] = typeof route === 'function' ? route() : route
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
      'GET api/person/p1/timeline': [401, { detail: 'Απαιτείται σύνδεση.' }],
    })
    const user = userEvent.setup()
    render(<App api={api} />)

    const timelineSelect = await screen.findByLabelText('Άτομο χρονογραμμής')
    await screen.findAllByRole('option', { name: /Συνθετικός Α/ })
    await user.selectOptions(timelineSelect, 'p1')

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
    expect(screen.queryByLabelText('Άτομο χρονογραμμής')).not.toBeInTheDocument()
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

    expect(await screen.findByLabelText('Άτομο χρονογραμμής')).toBeInTheDocument()
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
})
