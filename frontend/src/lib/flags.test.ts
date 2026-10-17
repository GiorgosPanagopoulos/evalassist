import { describe, expect, it } from 'vitest'
import { uiFlags } from './flags'

describe('uiFlags', () => {
  it('documentFile only with an explicit true from the server', () => {
    expect(uiFlags({ semantic_enabled: false, document_file_enabled: true }).documentFile).toBe(true)
    expect(uiFlags({ semantic_enabled: false, document_file_enabled: false }).documentFile).toBe(false)
    expect(uiFlags({ semantic_enabled: false }).documentFile).toBe(false)
    expect(uiFlags(undefined).documentFile).toBe(false)
  })
})
