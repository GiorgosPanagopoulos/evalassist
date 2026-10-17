import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import type { Me } from '../api/types'
import type { UiFlags } from '../lib/flags'
import { initialsOf } from '../lib/person'
import { ClockIcon, FlagIcon, TrendIcon } from './icons'

export type View = 'queries' | 'users' | 'password'

function RailButton({
  label,
  active,
  onClick,
  children,
}: {
  label: string
  active?: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      aria-current={active ? 'page' : undefined}
      className={`flex h-12 w-12 items-center justify-center rounded-xl ${
        active ? 'bg-navy text-gold' : 'text-muted hover:bg-navy/60 hover:text-ink'
      }`}
    >
      {children}
    </button>
  )
}

function UserMenu({
  me,
  onNavigate,
  onLogout,
}: {
  me: Me
  onNavigate: (view: View) => void
  onLogout: () => void
}) {
  const [open, setOpen] = useState(false)
  const menuId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    function onPointer(e: PointerEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false)
        buttonRef.current?.focus()
      }
    }
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  function pick(action: () => void) {
    setOpen(false)
    action()
  }

  const item = 'flex min-h-11 w-full items-center rounded-lg px-3 text-left text-[14px] text-ink hover:bg-navy'

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-label="Μενού χρήστη"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((o) => !o)}
        className="flex h-12 w-12 items-center justify-center rounded-full bg-navy text-[15px] font-bold text-gold ring-1 ring-line-strong"
      >
        {initialsOf(me.display_name ?? '') || initialsOf(me.username)}
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label="Λογαριασμός"
          className="absolute top-full right-0 z-40 mt-2 w-56 rounded-xl border border-line-strong bg-input p-1.5 shadow-[0_12px_32px_rgba(0,0,0,.5)] md:top-auto md:right-auto md:bottom-0 md:left-full md:mt-0 md:ml-3"
        >
          <div className="border-b border-line px-3 pt-2 pb-2.5">
            <span className="block text-[12px] text-muted">Συνδεδεμένος ως</span>
            <span aria-label="Συνδεδεμένος χρήστης" className="font-mono text-[13px] text-ink">
              {me.username}
            </span>
          </div>
          <div className="pt-1.5">
            {me.role === 'admin' && (
              <button type="button" role="menuitem" className={item} onClick={() => pick(() => onNavigate('users'))}>
                Χρήστες
              </button>
            )}
            <button type="button" role="menuitem" className={item} onClick={() => pick(() => onNavigate('password'))}>
              Κωδικός
            </button>
            <button type="button" role="menuitem" className={item} onClick={() => pick(onLogout)}>
              Αποσύνδεση
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

interface IconRailProps {
  me: Me
  view: View
  flags: UiFlags
  onNavigate: (view: View) => void
  onLogout: () => void
}

// Vertical 72px rail on desktop, a top bar on narrow screens.
export function IconRail({ me, view, flags, onNavigate, onLogout }: IconRailProps) {
  return (
    <nav
      aria-label="Κύρια πλοήγηση"
      className="no-print relative z-30 flex h-16 shrink-0 items-center gap-2 border-b border-line bg-rail px-3 md:sticky md:top-0 md:h-screen md:w-[72px] md:flex-col md:border-r md:border-b-0 md:px-0 md:py-4"
    >
      {/* 128px source: sharp at 40px on 2x displays. */}
      <img
        src={`${import.meta.env.BASE_URL}logo.png`}
        alt="EvalAssist"
        title="EvalAssist"
        width={40}
        height={40}
        className="mx-1 h-10 w-10 shrink-0 rounded-full border-[1.5px] border-gold bg-[#f7f4ec] object-cover md:mx-0 md:mb-4"
      />

      <div className="flex items-center gap-1 md:flex-col md:gap-2">
        <RailButton label="Ερωτήματα" active={view === 'queries'} onClick={() => onNavigate('queries')}>
          <TrendIcon size={20} />
        </RailButton>
        {flags.auditHistory && (
          <RailButton label="Ιστορικό ελέγχου" onClick={() => undefined}>
            <ClockIcon size={20} />
          </RailButton>
        )}
        {flags.reviewFlags && (
          <RailButton label="Σημάνσεις" onClick={() => undefined}>
            <FlagIcon size={20} />
          </RailButton>
        )}
      </div>

      <div className="ml-auto flex items-center gap-3 md:mt-auto md:ml-0 md:flex-col">
        <span className="rounded border border-line-strong px-1.5 py-0.5 font-mono text-[11px] tracking-[.08em] text-muted">
          BETA
        </span>
        <UserMenu me={me} onNavigate={onNavigate} onLogout={onLogout} />
      </div>
    </nav>
  )
}
