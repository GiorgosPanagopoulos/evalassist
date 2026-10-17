import { AlertIcon, CheckIcon } from './icons'

export type QueryMode = 'structured' | 'semantic'

export function ModeBadge({ mode }: { mode: QueryMode }) {
  if (mode === 'semantic') {
    return (
      <span
        data-testid="mode-badge"
        className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[12px] font-semibold"
        style={{ borderColor: 'rgba(212,169,58,.45)', backgroundColor: 'rgba(212,169,58,.1)', color: '#e8c25a' }}
      >
        <AlertIcon size={14} />
        LLM · επαλήθευσε τις πηγές
      </span>
    )
  }
  return (
    <span
      data-testid="mode-badge"
      className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[12px] font-semibold text-ok-text"
      style={{ borderColor: 'rgba(63,182,139,.45)', backgroundColor: 'rgba(63,182,139,.1)' }}
    >
      <CheckIcon size={14} />
      Ντετερμινιστικό · χωρίς LLM
    </span>
  )
}
