import { describe, expect, it } from 'vitest'
import { initialsOf } from './person'

describe('initialsOf', () => {
  it('takes the first letters of a Greek display name, capitals without tonos', () => {
    expect(initialsOf('Γεώργιος Παναγόπουλος')).toBe('ΓΠ')
    expect(initialsOf('Άννα Ήλιου')).toBe('ΑΗ')
  })

  it('splits a username on separators, else uses its first two letters', () => {
    expect(initialsOf('g.panagopoulos')).toBe('GP')
    expect(initialsOf('demo')).toBe('DE')
    expect(initialsOf('')).toBe('')
  })
})
