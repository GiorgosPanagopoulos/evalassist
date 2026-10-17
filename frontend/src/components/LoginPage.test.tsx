import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApiError } from '../api/client'
import type { Me } from '../api/types'
import { INSECURE_CONTEXT_TEXT, LoginPage, SESSION_NOT_STORED_TEXT } from './LoginPage'

const FROM_LOGIN: Me = { id: 2, username: 'alice', role: 'user', must_change_pw: false, features: { semantic_enabled: false } }
const FROM_ME: Me = { ...FROM_LOGIN, features: { semantic_enabled: false, document_file_enabled: true } }

function setup({
  secureContext,
  login = async () => FROM_LOGIN,
  me = async () => FROM_ME,
}: {
  secureContext?: boolean
  login?: () => Promise<Me>
  me?: () => Promise<Me>
} = {}) {
  const api = { login: vi.fn(login), me: vi.fn(me) }
  const onLoggedIn = vi.fn()
  render(<LoginPage api={api} onLoggedIn={onLoggedIn} secureContext={secureContext} />)
  return { api, onLoggedIn, user: userEvent.setup() }
}

async function submit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Όνομα χρήστη'), 'alice')
  await user.type(screen.getByLabelText('Κωδικός'), 'synthetic-pass-0001')
  await user.click(screen.getByRole('button', { name: 'Σύνδεση' }))
}

describe('LoginPage: μη ασφαλές context', () => {
  it('http: shows the banner and the form stays usable', async () => {
    const { api, user } = setup({ secureContext: false })

    expect(screen.getByTestId('insecure-context')).toHaveTextContent(INSECURE_CONTEXT_TEXT)
    expect(screen.getByTestId('insecure-context')).toHaveAttribute('role', 'alert')
    expect(screen.getByLabelText('Όνομα χρήστη')).toBeEnabled()
    expect(screen.getByLabelText('Κωδικός')).toBeEnabled()

    await submit(user)
    expect(api.login).toHaveBeenCalledTimes(1)
  })

  it('https or localhost: no banner', () => {
    setup({ secureContext: true })
    expect(screen.queryByTestId('insecure-context')).toBeNull()
    expect(screen.queryByText(INSECURE_CONTEXT_TEXT)).toBeNull()
  })
})

describe('LoginPage: έλεγχος ότι το session αποθηκεύτηκε', () => {
  it('login 200 and /me 200: logs in with the /me answer', async () => {
    const { api, onLoggedIn, user } = setup()
    await submit(user)

    expect(api.me).toHaveBeenCalledWith({ ignoreUnauthorized: true })
    expect(onLoggedIn).toHaveBeenCalledWith(FROM_ME)
  })

  it('login 200 and /me 401: explains, stays on the login page, clears the password', async () => {
    const { onLoggedIn, user } = setup({ me: () => Promise.reject(new ApiError(401, 'Απαιτείται σύνδεση.')) })
    await submit(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(SESSION_NOT_STORED_TEXT)
    expect(screen.queryByText('Απαιτείται σύνδεση.')).toBeNull()
    expect(onLoggedIn).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Κωδικός')).toHaveValue('')
  })

  it.each([
    ['500', () => Promise.reject(new ApiError(500, 'Internal server error'))],
    ['network error', () => Promise.reject(new TypeError('Failed to fetch'))],
  ])('login 200 and /me %s: continues with the login answer, as before', async (_, me) => {
    const { onLoggedIn, user } = setup({ me })
    await submit(user)

    expect(onLoggedIn).toHaveBeenCalledWith(FROM_LOGIN)
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('wrong credentials: the login error, no /me check', async () => {
    const { api, onLoggedIn, user } = setup({
      login: () => Promise.reject(new ApiError(401, 'Λάθος όνομα χρήστη ή κωδικός.')),
    })
    await submit(user)

    expect(await screen.findByRole('alert')).toHaveTextContent('Λάθος όνομα χρήστη ή κωδικός.')
    expect(api.me).not.toHaveBeenCalled()
    expect(onLoggedIn).not.toHaveBeenCalled()
  })
})
