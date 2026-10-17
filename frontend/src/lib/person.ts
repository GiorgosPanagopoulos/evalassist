import type { PersonOut } from '../api/types'

// Same format everywhere a person is named: search options, headings.
export function personLabel(person: PersonOut): string {
  return person.name ? `${person.name} (${person.person_id})` : `(${person.person_id})`
}

function capitals(letters: string): string {
  // Greek capitals carry no tonos.
  return letters.normalize('NFD').replace(/\p{M}/gu, '').toLocaleUpperCase('el-GR')
}

// "Γεώργιος Παναγόπουλος" -> "ΓΠ"; "g.panagopoulos" -> "GP"; "demo" -> "DE".
export function initialsOf(text: string): string {
  const words = text.split(/[\s._-]+/).filter((w) => /\p{L}/u.test(w))
  if (words.length >= 2) return capitals(words[0][0] + words[1][0])
  const letters = (words[0] ?? '').replace(/[^\p{L}]/gu, '')
  return capitals(letters.slice(0, 2))
}

function fold(text: string): string {
  // Accent and case insensitive; Latin M matches the Greek Μ of the codes.
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase('el-GR').replace(/m/g, 'μ')
}

export function matchesPerson(person: PersonOut, query: string): boolean {
  const q = fold(query.trim())
  if (!q) return true
  return fold(`${person.name} ${person.person_id}`).includes(q)
}
