import type {
  CreatedUser,
  HealthResponse,
  Me,
  PersonOut,
  SemanticQueryRequest,
  SemanticQueryResponse,
  StructuredQueryRequest,
  StructuredQueryResponse,
  TimelineResponse,
  UserOut,
  UserRole,
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

// Κενό base: τα paths ("api/...") είναι ΣΧΕΤΙΚΑ, χωρίς αρχικό "/", και
// λύνονται ως προς τη σελίδα. Κάτω από το portal (/evalassist/) πάνε στο
// /evalassist/api/..., τοπικά (Vite dev proxy) στο /api/... Same-origin και
// στις δύο περιπτώσεις, άρα το session cookie στέλνεται χωρίς CORS.
const DEFAULT_BASE_URL = ''

type FetchFn = typeof fetch

interface RequestOptions extends RequestInit {
  // Το 401 του login σημαίνει λάθος στοιχεία, όχι ληγμένο session.
  ignoreUnauthorized?: boolean
}

export class ApiClient {
  private baseUrl: string
  private fetchFn: FetchFn
  private unauthorizedHandler: (() => void) | null = null

  constructor(baseUrl: string = DEFAULT_BASE_URL, fetchFn: FetchFn = fetch) {
    this.baseUrl = baseUrl
    this.fetchFn = fetchFn === globalThis.fetch ? fetchFn.bind(globalThis) : fetchFn
  }

  // Καλείται σε κάθε 401 (χωρίς ή με ληγμένο session): η εφαρμογή γυρίζει στο login.
  setUnauthorizedHandler(handler: (() => void) | null): void {
    this.unauthorizedHandler = handler
  }

  private url(path: string): string {
    return this.baseUrl ? `${this.baseUrl}/${path}` : path
  }

  // Fetch και κοινός χειρισμός σφαλμάτων (detail, 503, 401) για όλα τα requests.
  private async send(path: string, init?: RequestOptions): Promise<Response> {
    const { ignoreUnauthorized, ...fetchInit } = init ?? {}
    const response = await this.fetchFn(this.url(path), {
      ...fetchInit,
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        ...fetchInit.headers,
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
      if (response.status === 401 && !ignoreUnauthorized) {
        this.unauthorizedHandler?.()
      }
      throw new ApiError(response.status, detail)
    }
    return response
  }

  private async request<T>(path: string, init?: RequestOptions): Promise<T> {
    const response = await this.send(path, init)
    if (response.status === 204) {
      return undefined as T
    }
    return response.json() as Promise<T>
  }

  // --- auth ---------------------------------------------------------------

  login(username: string, password: string): Promise<Me> {
    return this.request<Me>('api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
      ignoreUnauthorized: true,
    })
  }

  logout(): Promise<void> {
    return this.request<void>('api/auth/logout', { method: 'POST' })
  }

  me(): Promise<Me> {
    return this.request<Me>('api/auth/me')
  }

  changePassword(currentPassword: string, newPassword: string): Promise<void> {
    return this.request<void>('api/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    })
  }

  // --- admin --------------------------------------------------------------

  listUsers(): Promise<UserOut[]> {
    return this.request<UserOut[]>('api/admin/users')
  }

  createUser(username: string, role: UserRole): Promise<CreatedUser> {
    return this.request<CreatedUser>('api/admin/users', {
      method: 'POST',
      body: JSON.stringify({ username, role }),
    })
  }

  disableUser(userId: number): Promise<void> {
    return this.request<void>(`api/admin/users/${userId}/disable`, { method: 'POST' })
  }

  resetPassword(userId: number): Promise<{ temp_password: string }> {
    return this.request<{ temp_password: string }>(`api/admin/users/${userId}/reset-password`, {
      method: 'POST',
    })
  }

  // --- δεδομένα -----------------------------------------------------------

  getPersons(): Promise<PersonOut[]> {
    return this.request<PersonOut[]>('api/persons')
  }

  getPeriods(personId: string): Promise<string[]> {
    return this.request<string[]>(`api/persons/${encodeURIComponent(personId)}/periods`)
  }

  queryStructured(req: StructuredQueryRequest): Promise<StructuredQueryResponse> {
    return this.request<StructuredQueryResponse>('api/query/structured', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  }

  querySemantic(req: SemanticQueryRequest): Promise<SemanticQueryResponse> {
    return this.request<SemanticQueryResponse>('api/query/semantic', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  }

  getTimeline(personId: string): Promise<TimelineResponse> {
    return this.request<TimelineResponse>(`api/person/${encodeURIComponent(personId)}/timeline`)
  }

  // Το PDF ενός εγγράφου. Κάθε κλήση είναι ένα request και μία γραμμή audit
  // στον server: χωρίς cache του browser.
  async documentFile(personId: string, docId: string, period: string): Promise<Blob> {
    const path =
      `api/person/${encodeURIComponent(personId)}/documents/${encodeURIComponent(docId)}/file` +
      `?period=${encodeURIComponent(period)}`
    const response = await this.send(path, { cache: 'no-store', headers: { Accept: 'application/pdf' } })
    return response.blob()
  }

  getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>('api/health')
  }
}
