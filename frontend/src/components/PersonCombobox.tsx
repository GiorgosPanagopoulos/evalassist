import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import type { PersonOut } from '../api/types'
import { matchesPerson, personLabel } from '../lib/person'
import { SearchIcon } from './icons'

interface PersonComboboxProps {
  persons: PersonOut[]
  value: string
  onChange: (personId: string) => void
}

// ARIA 1.2 combobox with a listbox popup. Typing only filters the local list;
// nothing is fetched until an option is chosen.
export function PersonCombobox({ persons, value, onChange }: PersonComboboxProps) {
  const listboxId = useId()
  const optionId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)

  const selected = persons.find((p) => p.person_id === value) ?? null
  const matches = open ? persons.filter((p) => matchesPerson(p, query)) : []

  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
        openList()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function openList() {
    setQuery('')
    setActive(0)
    setOpen(true)
  }

  function close() {
    setOpen(false)
    setQuery('')
  }

  function choose(person: PersonOut) {
    close()
    if (person.person_id !== value) onChange(person.person_id)
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (!open) {
        openList()
        return
      }
      const step = e.key === 'ArrowDown' ? 1 : -1
      setActive((i) => (matches.length === 0 ? 0 : (i + step + matches.length) % matches.length))
    } else if (e.key === 'Enter') {
      // Never submit the toolbar form from the search field.
      e.preventDefault()
      if (open && matches[active]) choose(matches[active])
    } else if (e.key === 'Escape') {
      if (open) {
        e.preventDefault()
        close()
      }
    }
  }

  return (
    <div className="relative min-w-0 flex-[1_1_100%] lg:flex-[1_1_320px]">
      <div className="flex h-11 items-center gap-2.5 rounded-lg border border-line-strong bg-input px-3 focus-within:border-gold">
        <SearchIcon size={16} className="shrink-0 text-muted" />
        <input
          ref={inputRef}
          role="combobox"
          aria-label="Άτομο"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={open && matches[active] ? `${optionId}-${active}` : undefined}
          autoComplete="off"
          spellCheck={false}
          placeholder="Όνομα ή Α.Γ.Μ."
          value={open ? query : selected ? selected.name || selected.person_id : ''}
          onChange={(e) => {
            setQuery(e.target.value)
            setActive(0)
            setOpen(true)
          }}
          onClick={() => {
            if (!open) openList()
          }}
          onBlur={close}
          onKeyDown={handleKeyDown}
          className="h-full min-w-0 flex-1 bg-transparent text-[14px] text-ink placeholder:text-subtle focus:shadow-none"
          style={{ border: 'none', outline: 'none', boxShadow: 'none' }}
        />
        {selected && !open && (
          <span className="hidden shrink-0 font-mono text-[12px] text-muted sm:inline">{selected.person_id}</span>
        )}
        <kbd className="hidden shrink-0 rounded border border-line-strong px-1.5 py-0.5 font-mono text-[11px] text-muted md:inline">
          Ctrl K
        </kbd>
      </div>

      <ul
        id={listboxId}
        role="listbox"
        aria-label="Άτομα"
        hidden={!open}
        className="absolute top-[calc(100%+6px)] right-0 left-0 z-30 max-h-80 overflow-y-auto rounded-lg border border-line-strong bg-input py-1 shadow-[0_12px_32px_rgba(0,0,0,.45)]"
      >
        {matches.map((p, i) => (
          <li
            key={p.person_id}
            id={`${optionId}-${i}`}
            role="option"
            aria-label={personLabel(p)}
            aria-selected={p.person_id === value}
            // Keep focus in the input so blur does not close before the click.
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => choose(p)}
            onMouseEnter={() => setActive(i)}
            className={`flex min-h-11 cursor-pointer items-center justify-between gap-3 px-3 text-[14px] ${
              i === active ? 'bg-navy text-ink' : 'text-ink'
            }`}
          >
            <span className="truncate">{p.name || p.person_id}</span>
            <span className="shrink-0 font-mono text-[12px] text-muted">{p.person_id}</span>
          </li>
        ))}
        {open && matches.length === 0 && <li className="px-3 py-3 text-[13px] text-muted">Κανένα αποτέλεσμα</li>}
      </ul>
    </div>
  )
}
