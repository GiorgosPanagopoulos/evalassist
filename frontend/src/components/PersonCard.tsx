import type { PersonOut, TimelinePoint } from '../api/types'
import { formatScore, timelineStats } from '../lib/timeline'
import { ModeBadge, type QueryMode } from './ModeBadge'
import { initialsOf, personLabel } from '../lib/person'

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'danger' }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[11px] font-semibold tracking-[.08em] text-muted uppercase">{label}</dt>
      <dd className={`text-[24px] leading-none font-semibold ${tone === 'danger' ? 'text-danger-soft' : 'text-ink'}`}>
        {value}
      </dd>
    </div>
  )
}

interface PersonCardProps {
  person: PersonOut
  points: TimelinePoint[] | null
  mode: QueryMode
}

export function PersonCard({ person, points, mode }: PersonCardProps) {
  const stats = points ? timelineStats(points) : null
  const show = (value: number | null | undefined) => (value === null || value === undefined ? '-' : formatScore(value))

  return (
    <div className="flex flex-wrap items-center gap-x-8 gap-y-5 rounded-2xl border border-line bg-card px-5 py-5 sm:px-7">
      <div className="flex min-w-0 flex-[1_1_260px] items-center gap-4">
        <span
          aria-hidden="true"
          className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border-2 border-gold bg-navy text-[18px] font-bold text-gold sm:h-16 sm:w-16 sm:text-[20px]"
        >
          {initialsOf(person.name) || initialsOf(person.person_id)}
        </span>
        <div data-testid="timeline-person" className="flex min-w-0 flex-col gap-1">
          <span className="sr-only">Άτομο: {personLabel(person)}</span>
          <h2 aria-hidden="true" className="truncate text-[20px] font-semibold text-ink uppercase sm:text-[24px]">
            {person.name || person.person_id}
          </h2>
          <span aria-hidden="true" className="font-mono text-[13px] text-muted">
            {person.person_id}
          </span>
        </div>
      </div>

      <dl className="flex flex-wrap items-end gap-x-8 gap-y-3">
        <Stat label="Περίοδοι" value={stats ? String(stats.periods) : '-'} />
        <Stat label="Μέσος" value={show(stats?.mean)} />
        <Stat label="Ελάχιστο" value={show(stats?.min)} tone="danger" />
        <Stat label="Τελευταίος" value={show(stats?.last)} />
      </dl>

      <ModeBadge mode={mode} />
    </div>
  )
}
