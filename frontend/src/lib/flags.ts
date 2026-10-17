import type { Features } from '../api/types'

export interface UiFlags {
  semantic: boolean
  documentFile: boolean
  reviewFlags: boolean
  auditHistory: boolean
  export: boolean
}

// Missing from the server means off: only an explicit true turns a flag on.
export function uiFlags(features: Features | undefined): UiFlags {
  return {
    semantic: features?.semantic_enabled === true,
    documentFile: features?.document_file_enabled === true,
    reviewFlags: features?.review_flags_enabled === true,
    auditHistory: features?.audit_history_enabled === true,
    export: features?.export_enabled === true,
  }
}
