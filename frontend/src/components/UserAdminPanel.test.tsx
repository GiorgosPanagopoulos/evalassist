import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApiError } from '../api/client'
import type { UserOut } from '../api/types'
import { UserAdminPanel, type UserAdminApi } from './UserAdminPanel'

const USERS: UserOut[] = [
  { id: 1, username: 'root', role: 'admin', is_active: true, must_change_pw: false, locked: false, created_at: '' },
  { id: 2, username: 'alice', role: 'user', is_active: true, must_change_pw: true, locked: false, created_at: '' },
]

function makeFakeApi(overrides: Partial<UserAdminApi> = {}): UserAdminApi {
  return {
    listUsers: vi.fn(async () => USERS),
    createUser: vi.fn(async (username: string, role) => ({ id: 3, username, role, temp_password: 'TEMP-synthetic-16' })),
    disableUser: vi.fn(async () => undefined),
    resetPassword: vi.fn(async () => ({ temp_password: 'RESET-synthetic-16' })),
    ...overrides,
  }
}

describe('UserAdminPanel', () => {
  it('lists users with their status', async () => {
    render(<UserAdminPanel api={makeFakeApi()} />)

    expect(await screen.findByRole('cell', { name: 'alice' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'αναμονή αλλαγής κωδικού' })).toBeInTheDocument()
  })

  it('creates a user and shows the temporary password once', async () => {
    const api = makeFakeApi()
    const user = userEvent.setup()
    render(<UserAdminPanel api={api} />)

    await user.type(screen.getByLabelText('Νέο όνομα χρήστη'), 'carol')
    await user.click(screen.getByRole('button', { name: 'Δημιουργία' }))

    expect(api.createUser).toHaveBeenCalledWith('carol', 'user')
    expect(await screen.findByRole('status')).toHaveTextContent('TEMP-synthetic-16')

    // Η επόμενη ενέργεια σβήνει τον προηγούμενο προσωρινό κωδικό από την οθόνη.
    await user.click(await screen.findByRole('button', { name: 'Νέος προσωρινός κωδικός για alice' }))
    expect(await screen.findByRole('status')).toHaveTextContent('RESET-synthetic-16')
    expect(screen.queryByText('TEMP-synthetic-16')).not.toBeInTheDocument()
  })

  it('disable needs a confirmation click', async () => {
    const api = makeFakeApi()
    const user = userEvent.setup()
    render(<UserAdminPanel api={api} />)

    await user.click(await screen.findByRole('button', { name: 'Απενεργοποίηση alice' }))
    expect(api.disableUser).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Επιβεβαίωση απενεργοποίησης alice' }))
    expect(api.disableUser).toHaveBeenCalledWith(2)
  })

  it('shows the backend error', async () => {
    const api = makeFakeApi({
      disableUser: vi.fn(async () => {
        throw new ApiError(403, 'Λογαριασμοί admin διαχειρίζονται μόνο από το CLI.')
      }),
    })
    const user = userEvent.setup()
    render(<UserAdminPanel api={api} />)

    await user.click(await screen.findByRole('button', { name: 'Απενεργοποίηση alice' }))
    await user.click(screen.getByRole('button', { name: 'Επιβεβαίωση απενεργοποίησης alice' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('μόνο από το CLI')
  })

  it('offers no disable or reset for an admin row, but does for a user row', async () => {
    render(<UserAdminPanel api={makeFakeApi()} />)

    expect(await screen.findByRole('button', { name: 'Απενεργοποίηση alice' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Νέος προσωρινός κωδικός για alice' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Απενεργοποίηση root' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Νέος προσωρινός κωδικός για root' })).not.toBeInTheDocument()
  })

  it('the create form offers no admin role', async () => {
    render(<UserAdminPanel api={makeFakeApi()} />)

    await screen.findByRole('cell', { name: 'alice' })
    expect(screen.queryByLabelText('Ρόλος')).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'admin' })).not.toBeInTheDocument()
  })
})
