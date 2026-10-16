import type { PersonOut } from '../api/types'

// Ίδια μορφή με τις επιλογές του dropdown «Άτομο» στο QueryForm.
function personLabel(person: PersonOut): string {
  return person.name ? `${person.name} (${person.person_id})` : `(${person.person_id})`
}

// Ρητά σε ποιον αφορά το περιεχόμενο από κάτω: ποτέ αποτελέσματα χωρίς άτομο.
export function PersonHeading({ person, testId }: { person: PersonOut; testId: string }) {
  return (
    <p data-testid={testId} className="text-[13px] font-semibold" style={{ color: '#f2f2f4' }}>
      Άτομο: {personLabel(person)}
    </p>
  )
}
