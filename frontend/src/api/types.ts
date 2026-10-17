// Mirrors backend/app/api/schemas.py and backend/app/retrieval/models.py.
// Field names must match exactly (snake_case, as returned by FastAPI).

export type RetrievalMode = 'structured' | 'semantic'

export interface PersonOut {
  person_id: string
  name: string
}

export type StructuredOperation =
  | 'get_scores'
  | 'compare_periods'
  | 'top_bottom_sections'
  | 'get_promotions_table'
  | 'get_service_time_table'

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

// Παραπομπή δομημένης απάντησης (backend StructuredCitation). page `null` =
// η σελίδα δεν καταγράφηκε στη DB (π.χ. promotions, service_time).
export interface StructuredCitation {
  doc_id: string
  page: number | null
  section: string
}

// Το ολιστικό πεδίο (field_code 141) που το top_bottom_sections επιστρέφει στο
// `data.overall`, χωριστά από την κατάταξη. `null` = δεν υπάρχει στην περίοδο.
export interface OverallFieldScore {
  field_code: string
  description: string
  value: number
}

export interface StructuredResult {
  mode: 'structured'
  data: Record<string, unknown>
  citations: StructuredCitation[]
  retrieved_doc_ids: string[]
}

export interface SemanticResult {
  mode: 'semantic'
  answer: string
  citations: Citation[]
  retrieved_doc_ids: string[]
  model: string
  routing_hint: string | null
  // Precheck refusal code (app.retrieval.precheck.RefusalReason).
  // string, not a union: an unknown code must not break the type.
  refusal_reason?: string | null
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
  // null: δεν ελέγχθηκε (semantic κλειστό, ο server δεν καλεί το Ollama).
  ollama_reachable: boolean | null
}

// Mirrors backend/app/retrieval/timeline.py + backend/app/api/routes_timeline.py.
export type TimelineKind = 'Ε.Α.' | 'Σ.Α.'

export interface TimelinePoint {
  period: string
  period_start: string
  kind: TimelineKind
  // null για Σ.Α. (χωρίς αριθμητική βαθμολογία) — ποτέ interpolation.
  score: number | null
  doc_id: string
  page: number | null
  section: string
}

export interface TimelineResult {
  person_id: string
  points: TimelinePoint[]
  retrieved_doc_ids: string[]
}

export interface TimelineResponse {
  result: TimelineResult
  audit_id: number
}

// --- auth / admin (mirrors backend/app/api/schemas.py) ---

export type UserRole = 'admin' | 'user'

export interface Features {
  semantic_enabled: boolean
  // Από τον server: true μόνο όταν το DOCS_ROOT είναι ρυθμισμένος φάκελος.
  // Optional ώστε ένας παλαιότερος server να σημαίνει false.
  document_file_enabled?: boolean
  // UI flags for endpoints that do not exist yet. Absent means false.
  review_flags_enabled?: boolean
  audit_history_enabled?: boolean
  export_enabled?: boolean
}

export interface Me {
  id: number
  username: string
  // Not sent by the backend yet; avatar initials fall back to the username.
  display_name?: string | null
  role: UserRole
  must_change_pw: boolean
  features: Features
}

export interface UserOut {
  id: number
  username: string
  role: UserRole
  is_active: boolean
  must_change_pw: boolean
  locked: boolean
  created_at: string
}

export interface CreatedUser {
  id: number
  username: string
  role: UserRole
  temp_password: string
}
