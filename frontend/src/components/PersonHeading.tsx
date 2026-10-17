import type { PersonOut } from '../api/types'
import { personLabel } from '../lib/person'

// Ρητά σε ποιον αφορά το περιεχόμενο από κάτω: ποτέ αποτελέσματα χωρίς άτομο.
export function PersonHeading({ person, testId }: { person: PersonOut; testId: string }) {
  return (
    <p data-testid={testId} className="text-[13px] font-semibold text-ink">
      Άτομο: {personLabel(person)}
    </p>
  )
}
