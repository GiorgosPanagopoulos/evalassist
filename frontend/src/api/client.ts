import type {
  HealthResponse,
  PersonOut,
  SemanticQueryRequest,
  SemanticQueryResponse,
  StructuredQueryRequest,
  StructuredQueryResponse,
} from './types'

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

const DEFAULT_BASE_URL = 'http://localhost:8000'

type FetchFn = typeof fetch

export class ApiClient {
  private baseUrl: string
  private fetchFn: FetchFn

  constructor(baseUrl?: string, fetchFn: FetchFn = fetch) {
    this.baseUrl = baseUrl ?? import.meta.env.VITE_API_URL ?? DEFAULT_BASE_URL
    this.fetchFn = fetchFn
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await this.fetchFn(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...init?.headers,
      },
    })

    if (!response.ok) {
      let detail = response.statusText
      try {
        const body = await response.json()
        detail = body?.detail ?? detail
      } catch {
        // response had no JSON body; fall back to statusText
      }
      if (response.status === 503) {
        detail = 'LLM μη διαθέσιμο'
      }
      throw new ApiError(response.status, detail)
    }

    return response.json() as Promise<T>
  }

  getPersons(): Promise<PersonOut[]> {
    return this.request<PersonOut[]>('/persons')
  }

  getPeriods(personId: string): Promise<string[]> {
    return this.request<string[]>(`/persons/${encodeURIComponent(personId)}/periods`)
  }

  queryStructured(req: StructuredQueryRequest): Promise<StructuredQueryResponse> {
    return this.request<StructuredQueryResponse>('/query/structured', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  }

  querySemantic(req: SemanticQueryRequest): Promise<SemanticQueryResponse> {
    return this.request<SemanticQueryResponse>('/query/semantic', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  }

  getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>('/health')
  }
}
