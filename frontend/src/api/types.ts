// Mirrors backend/app/api/schemas.py and backend/app/retrieval/models.py.
// Field names must match exactly (snake_case, as returned by FastAPI).

export type RetrievalMode = 'structured' | 'semantic'

export interface PersonOut {
  person_id: string
  name: string
}

export type StructuredOperation = 'get_scores' | 'compare_periods' | 'top_bottom_sections'

export interface StructuredQueryRequest {
  person_id: string
  period: string
  operation: StructuredOperation
  other_period?: string
  n?: number
}

export interface SemanticQueryRequest {
  person_id: string
  period: string
  question: string
}

export interface Citation {
  doc_id: string
  page: number
  section: string
  score: number
}

export interface StructuredResult {
  mode: 'structured'
  data: Record<string, unknown>
  sources: Record<string, string>[]
  retrieved_doc_ids: string[]
}

export interface SemanticResult {
  mode: 'semantic'
  answer: string
  citations: Citation[]
  retrieved_doc_ids: string[]
  model: string
  routing_hint: string | null
}

export interface StructuredQueryResponse {
  result: StructuredResult
  audit_id: number
}

export interface SemanticQueryResponse {
  result: SemanticResult
  audit_id: number
}

export interface HealthResponse {
  status: string
  ollama_reachable: boolean
}
