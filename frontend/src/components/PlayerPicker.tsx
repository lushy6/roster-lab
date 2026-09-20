import { useEffect, useRef, useState } from 'react'
import { searchPlayers, type PlayerSearch } from '../api'

type Props = {
  label: string
  placeholder: string
  season: number
  values: number[]
  onChange: (ids: number[]) => void
  disabled?: boolean
}

export default function PlayerPicker({ label, placeholder, season, values, onChange, disabled }: Props) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [results, setResults] = useState<PlayerSearch[]>([])
  const [active, setActive] = useState(0)
  const wrapRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open || q.trim().length < 1) { setResults([]); return }
    const t = setTimeout(async () => {
      try { setResults(await searchPlayers(season, q.trim(), 8)) } catch { setResults([]) }
    }, 150)
    return () => clearTimeout(t)
  }, [q, season, open])

  useEffect(() => {
    const h = (e: MouseEvent) => { if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false) }
    window.addEventListener('mousedown', h)
    return () => window.removeEventListener('mousedown', h)
  }, [])

  const add = (id: number) => {
    if (values.includes(id)) return
    onChange([...values, id])
    setQ(''); setOpen(false); setResults([])
    inputRef.current?.focus()
  }
  const remove = (id: number) => onChange(values.filter(v => v !== id))

  // resolve names for pills - we show ID + fetch name if needed via results cache
  const pillLabel = (id: number) => {
    const hit = results.find(r => r.id === id)
    return hit ? `${hit.name} · ${hit.team}` : `#${id}`
  }

  return (
    <div className="picker" ref={wrapRef}>
      <label className="picker-label">{label}
        <div className="picker-input-wrap">
          <input
            ref={inputRef}
            value={q}
            disabled={disabled}
            placeholder={placeholder}
            onFocus={() => setOpen(true)}
            onChange={e => { setQ(e.target.value); setOpen(true); setActive(0) }}
            onKeyDown={e => {
              if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, results.length - 1)) }
              else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)) }
              else if (e.key === 'Enter' && results[active]) { e.preventDefault(); add(results[active].id) }
              else if (e.key === 'Escape') setOpen(false)
            }}
            aria-expanded={open}
            aria-autocomplete="list"
          />
          <span className="picker-count">{values.length ? `${values.length} selected` : ''}</span>
        </div>
      </label>

      {values.length > 0 && (
        <div className="picker-pills">
          {values.map(id => (
            <span key={id} className="picker-pill">
              {pillLabel(id)}
              <button type="button" aria-label={`Remove ${id}`} onClick={() => remove(id)}>×</button>
            </span>
          ))}
        </div>
      )}

      {open && q.trim().length >= 1 && (
        <div className="picker-popover" role="listbox">
          {results.length === 0 ? (
            <div className="picker-empty">No players match “{q}”.</div>
          ) : results.map((p, i) => (
            <button
              key={p.id}
              type="button"
              role="option"
              aria-selected={i === active}
              className={`picker-option ${i === active ? 'is-active' : ''} ${!p.is_priced ? 'is-unpriced' : ''}`}
              onMouseEnter={() => setActive(i)}
              onClick={() => add(p.id)}
            >
              <span className="picker-opt-name"><strong>{p.name}</strong><small>{p.team} · {p.primary_position} {p.eligible_positions.join('/')}</small></span>
              <span className="picker-opt-meta">
                <em>{p.war.toFixed(1)} WAR</em>
                <span>{p.is_priced && p.salary ? `$${(p.salary/1_000_000).toFixed(1)}m` : 'no salary'}</span>
              </span>
            </button>
          ))}
          <div className="picker-hint">↑↓ navigate · Enter select · Esc close</div>
        </div>
      )}
    </div>
  )
}
