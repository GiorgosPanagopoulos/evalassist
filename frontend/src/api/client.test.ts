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
  it('getPersons requests GET /persons and parses JSON', async () => {
    const persons = [{ person_id: 'p1', name: 'Άννα' }]
    const fetchFn = fakeFetch(200, persons)
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)

    const result = await client.getPersons()

    expect(result).toEqual(persons)
    expect(fetchFn).toHaveBeenCalledWith(
      `${BASE_URL}/persons`,
      expect.objectContaining({ headers: expect.objectContaining({ 'Content-Type': 'application/json' }) }),
    )
  })

  it('getPeriods requests GET /persons/{id}/periods with encoded id', async () => {
    const periods = ['2024-Q1', '2024-Q2']
    const fetchFn = fakeFetch(200, periods)
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)

    const result = await client.getPeriods('p 1')

    expect(result).toEqual(periods)
    expect(fetchFn).toHaveBeenCalledWith(`${BASE_URL}/persons/p%201/periods`, expect.anything())
  })

  it('queryStructured POSTs the exact request body to /query/structured', async () => {
    const response = { result: { mode: 'structured', data: {}, sources: [], retrieved_doc_ids: [] }, audit_id: 7 }
    const fetchFn = fakeFetch(200, response)
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)

    const req = { person_id: 'p1', period: '2024-Q1', operation: 'get_scores' as const }
    const result = await client.queryStructured(req)

    expect(result).toEqual(response)
    const [url, init] = fetchFn.mock.calls[0]
    expect(url).toBe(`${BASE_URL}/query/structured`)
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
    expect(url).toBe(`${BASE_URL}/query/semantic`)
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toEqual(req)
  })

  it('getHealth requests GET /health', async () => {
    const health = { status: 'ok', ollama_reachable: true }
    const fetchFn = fakeFetch(200, health)
    const client = new ApiClient(BASE_URL, fetchFn as unknown as typeof fetch)

    const result = await client.getHealth()

    expect(result).toEqual(health)
    expect(fetchFn).toHaveBeenCalledWith(`${BASE_URL}/health`, expect.anything())
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
})
