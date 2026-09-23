import { useEffect, useId, useRef, useState } from 'react'
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
  const [resultsFor, setResultsFor] = useState('') // the query the current results answer, so Enter can't pick from an older one
  const [active, setActive] = useState(0)
  // Names of everyone added here, so pills keep reading "Aaron Judge · Team" after the search clears.
  const [labels, setLabels] = useState<Record<number, string>>({})
  const wrapRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listId = useId()

  useEffect(() => {
    if (!open || q.trim().length < 1) { setResults([]); return }
    let stale = false // a slow earlier response must not overwrite a newer one
    const query = q.trim()
    const timer = setTimeout(async () => {
      try {
        const found = await searchPlayers(season, query, 8)
        if (!stale) { setResults(found); setResultsFor(query); setActive(0) }
      } catch {
        if (!stale) setResults([])
      }
    }, 150)
    return () => { stale = true; clearTimeout(timer) }
  }, [q, season, open])

  useEffect(() => {
    const h = (e: MouseEvent) => { if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false) }
    window.addEventListener('mousedown', h)
    return () => window.removeEventListener('mousedown', h)
  }, [])

  const add = (player: PlayerSearch) => {
    if (values.includes(player.id)) return
    setLabels(prev => ({ ...prev, [player.id]: `${player.name} · ${player.team}` }))
    onChange([...values, player.id])
    setQ(''); setOpen(false); setResults([])
    inputRef.current?.focus()
  }
  const remove = (id: number) => onChange(values.filter(v => v !== id))
  const pillLabel = (id: number) => labels[id] ?? `#${id}`
  const showList = open && q.trim().length >= 1
  const optionId = (index: number) => `${listId}-option-${index}`

  return (
    <div className="picker" ref={wrapRef}>
      <label className="picker-label">{label}
        <div className="picker-input-wrap">
          <input
            ref={inputRef}
            role="combobox"
            value={q}
            disabled={disabled}
            placeholder={placeholder}
            onFocus={() => setOpen(true)}
            onChange={e => { setQ(e.target.value); setOpen(true); setActive(0) }}
            onKeyDown={e => {
              if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.max(0, Math.min(a + 1, results.length - 1))) }
              else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)) }
              else if (e.key === 'Enter' && results[active] && resultsFor === q.trim()) { e.preventDefault(); add(results[active]) }
              else if (e.key === 'Escape') setOpen(false)
            }}
            aria-label={label}
            aria-expanded={showList}
            aria-controls={results.length ? listId : undefined}
            aria-activedescendant={showList && results[active] ? optionId(active) : undefined}
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
              <button type="button" aria-label={`Remove ${pillLabel(id)}`} onClick={() => remove(id)}>×</button>
            </span>
          ))}
        </div>
      )}

      {showList && (
        <div className="picker-popover">
          {results.length === 0 ? (
            <div className="picker-empty">No players match “{q}”.</div>
          ) : (
            <div role="listbox" id={listId} aria-label={`${label} suggestions`}>
              {results.map((p, i) => (
                <button
                  key={p.id}
                  id={optionId(i)}
                  type="button"
                  role="option"
                  tabIndex={-1}
                  aria-selected={i === active}
                  className={`picker-option ${i === active ? 'is-active' : ''} ${!p.is_priced ? 'is-unpriced' : ''}`}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => add(p)}
                >
                  <span className="picker-opt-name"><strong>{p.name}</strong><small>{p.team} · {p.primary_position} {p.eligible_positions.join('/')}</small></span>
                  <span className="picker-opt-meta">
                    <em>{p.war.toFixed(1)} WAR</em>
                    <span>{p.is_priced && p.salary ? `$${(p.salary/1_000_000).toFixed(1)}m` : 'no salary'}</span>
                  </span>
                </button>
              ))}
            </div>
          )}
          <div className="picker-hint">↑↓ navigate · Enter select · Esc close</div>
        </div>
      )}
    </div>
  )
}
