import { describe, expect, it, vi } from 'vitest'
import { ApiClient, ApiError } from './client'

const BASE_URL = 'http://fake-api.test'

function fakeFetch(status: number, body: unknown) {
  return vi.fn(async (_url: string, _init?: RequestInit) => {
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  })
}

describe('ApiClient', () => {
  it('getPersons requests GET api/persons and parses JSON', async () => {
    const persons = [{ person_id: 'p1', name: 'Άννα' }]
    const fetchFn = fakeFetch(200, persons)
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)

    const result = await client.getPersons()

    expect(result).toEqual(persons)
    expect(fetchFn).toHaveBeenCalledWith(
      `${BASE_URL}/api/persons`,
      expect.objectContaining({ headers: expect.objectContaining({ 'Content-Type': 'application/json' }) }),
    )
  })

  it('getPeriods requests GET api/persons/{id}/periods with encoded id', async () => {
    const periods = ['2024-Q1', '2024-Q2']
    const fetchFn = fakeFetch(200, periods)
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)

    const result = await client.getPeriods('p 1')

    expect(result).toEqual(periods)
    expect(fetchFn).toHaveBeenCalledWith(`${BASE_URL}/api/persons/p%201/periods`, expect.anything())
  })

  it('queryStructured POSTs the exact request body to /query/structured', async () => {
    const response = { result: { mode: 'structured', data: {}, citations: [], retrieved_doc_ids: [] }, audit_id: 7 }
    const fetchFn = fakeFetch(200, response)
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)

    const req = { person_id: 'p1', period: '2024-Q1', operation: 'get_scores' as const }
    const result = await client.queryStructured(req)

    expect(result).toEqual(response)
    const [url, init] = fetchFn.mock.calls[0]
    expect(url).toBe(`${BASE_URL}/api/query/structured`)
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toEqual(req)
  })

  it('querySemantic POSTs the exact request body to /query/semantic', async () => {
    const response = {
      result: { mode: 'semantic', answer: 'ok', citations: [], retrieved_doc_ids: [], model: 'qwen2.5:14b' },
      audit_id: 8,
    }
    const fetchFn = fakeFetch(200, response)
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)

    const req = { person_id: 'p1', period: '2024-Q1', question: 'Πώς πήγε;' }
    const result = await client.querySemantic(req)

    expect(result).toEqual(response)
    const [url, init] = fetchFn.mock.calls[0]
    expect(url).toBe(`${BASE_URL}/api/query/semantic`)
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toEqual(req)
  })

  it('getHealth requests GET /health', async () => {
    const health = { status: 'ok', ollama_reachable: true }
    const fetchFn = fakeFetch(200, health)
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)

    const result = await client.getHealth()

    expect(result).toEqual(health)
    expect(fetchFn).toHaveBeenCalledWith(`${BASE_URL}/api/health`, expect.anything())
  })

  it('maps a 400 response to ApiError with the backend detail', async () => {
    const fetchFn = fakeFetch(400, { detail: 'person_id εκτός εύρους' })
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)

    await expect(client.getPersons()).rejects.toMatchObject(
      new ApiError(400, 'person_id εκτός εύρους'),
    )
  })

  it('maps a 422 response to ApiError with the backend detail', async () => {
    const fetchFn = fakeFetch(422, { detail: 'question πρέπει να έχει τουλάχιστον 3 χαρακτήρες' })
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)

    await expect(client.querySemantic({ person_id: 'p1', period: '2024-Q1', question: 'hi' })).rejects.toMatchObject(
      { status: 422, detail: 'question πρέπει να έχει τουλάχιστον 3 χαρακτήρες' },
    )
  })

  it('maps a 503 response to an ApiError with the LLM unavailable message', async () => {
    const fetchFn = fakeFetch(503, { detail: 'Το τοπικό LLM δεν είναι διαθέσιμο.' })
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)

    await expect(client.getHealth()).rejects.toMatchObject({ status: 503, detail: 'LLM μη διαθέσιμο' })
  })

  it('calls the default fetch without Illegal invocation when no fetchFn is injected', async () => {
    const nativeLikeFetch = vi.fn(function (this: unknown) {
      if (this !== globalThis) {
        throw new TypeError('Illegal invocation')
      }
      return Promise.resolve(
        new Response(JSON.stringify({ status: 'ok', ollama_reachable: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    })
    vi.stubGlobal('fetch', nativeLikeFetch)

    const client = new ApiClient(BASE_URL)

    await expect(client.getHealth()).resolves.toEqual({ status: 'ok', ollama_reachable: true })

    vi.unstubAllGlobals()
  })

  it('uses a RELATIVE api/ path (no leading slash) by default, so it resolves under any subpath', async () => {
    const fetchFn = fakeFetch(200, { status: 'ok', ollama_reachable: true })
    const client = new ApiClient(undefined, fetchFn as unknown as typeof fetch)

    await client.getHealth()

    expect(fetchFn.mock.calls[0][0]).toBe('api/health')
  })

  it("sends credentials: 'same-origin' on every request", async () => {
    const fetchFn = fakeFetch(200, [])
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)

    await client.getPersons()
    await client.login('alice', 'synthetic-pass')

    for (const [, init] of fetchFn.mock.calls) {
      expect(init?.credentials).toBe('same-origin')
    }
  })

  it('calls the unauthorized handler on 401 and still rejects', async () => {
    const fetchFn = fakeFetch(401, { detail: 'Απαιτείται σύνδεση.' })
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)
    const onUnauthorized = vi.fn()
    client.setUnauthorizedHandler(onUnauthorized)

    await expect(client.getPersons()).rejects.toMatchObject({ status: 401 })
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('does NOT call the unauthorized handler for a failed login (wrong credentials)', async () => {
    const fetchFn = fakeFetch(401, { detail: 'Λάθος όνομα χρήστη ή κωδικός.' })
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)
    const onUnauthorized = vi.fn()
    client.setUnauthorizedHandler(onUnauthorized)

    await expect(client.login('alice', 'wrong')).rejects.toMatchObject({
      status: 401,
      detail: 'Λάθος όνομα χρήστη ή κωδικός.',
    })
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('login POSTs the credentials to api/auth/login', async () => {
    const me = { id: 1, username: 'alice', role: 'user', must_change_pw: false }
    const fetchFn = fakeFetch(200, me)
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)

    await expect(client.login('alice', 'synthetic-pass')).resolves.toEqual(me)
    const [url, init] = fetchFn.mock.calls[0]
    expect(url).toBe(`${BASE_URL}/api/auth/login`)
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toEqual({ username: 'alice', password: 'synthetic-pass' })
  })

  it('resolves 204 responses (logout) without parsing a body', async () => {
    const fetchFn = vi.fn(async (_url: string, _init?: RequestInit) => new Response(null, { status: 204 }))
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)

    await expect(client.logout()).resolves.toBeUndefined()
    expect(fetchFn.mock.calls[0][0]).toBe(`${BASE_URL}/api/auth/logout`)
  })
})

describe('ApiClient.documentFile', () => {
  function pdfFetch(status: number) {
    return vi.fn(async (_url: string, _init?: RequestInit) =>
      status === 200
        ? new Response('%PDF-1.4 synthetic', { status, headers: { 'Content-Type': 'application/pdf' } })
        : new Response(JSON.stringify({ detail: 'Δεν βρέθηκε το έγγραφο.' }), {
            status,
            headers: { 'Content-Type': 'application/json' },
          }),
    )
  }

  it('GETs the file with encoded person, doc and period, no-store, same-origin cookie', async () => {
    const fetchFn = pdfFetch(200)
    const client = new ApiClient('', fetchFn as unknown as typeof fetch)

    const blob = await client.documentFile('Μ-01253', 'doc/1', '2012-09-14..2012-12-31')

    expect(await blob.text()).toBe('%PDF-1.4 synthetic')
    expect(fetchFn).toHaveBeenCalledTimes(1)
    const [url, init] = fetchFn.mock.calls[0]
    expect(url).toBe(
      `api/person/${encodeURIComponent('Μ-01253')}/documents/doc%2F1/file?period=2012-09-14..2012-12-31`,
    )
    // Το fragment της σελίδας δεν φτάνει ποτέ στον server.
    expect(url).not.toContain('#')
    expect(init?.cache).toBe('no-store')
    expect(init?.credentials).toBe('same-origin')
  })

  it('404 throws ApiError(404) without calling the unauthorized handler', async () => {
    const client = new ApiClient('', pdfFetch(404) as unknown as typeof fetch)
    const onUnauthorized = vi.fn()
    client.setUnauthorizedHandler(onUnauthorized)

    await expect(client.documentFile('p1', 'd1', 'x')).rejects.toMatchObject({ status: 404 })
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('401 calls the unauthorized handler', async () => {
    const client = new ApiClient('', pdfFetch(401) as unknown as typeof fetch)
    const onUnauthorized = vi.fn()
    client.setUnauthorizedHandler(onUnauthorized)

    await expect(client.documentFile('p1', 'd1', 'x')).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })
})

describe('ApiClient.me', () => {
  it('ignoreUnauthorized: a 401 does not call the unauthorized handler', async () => {
    const client = new ApiClient('', fakeFetch(401, { detail: 'Απαιτείται σύνδεση.' }) as unknown as typeof fetch)
    const onUnauthorized = vi.fn()
    client.setUnauthorizedHandler(onUnauthorized)

    await expect(client.me({ ignoreUnauthorized: true })).rejects.toMatchObject({ status: 401 })
    expect(onUnauthorized).not.toHaveBeenCalled()

    // Χωρίς την επιλογή, όπως πριν: ο handler καλείται.
    await expect(client.me()).rejects.toMatchObject({ status: 401 })
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })
})
