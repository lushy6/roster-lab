import { useEffect, useState } from 'react'
import { API } from '../api'

type Missing = { id: number; name: string; team: string; primary_position: string }
type Coverage = { priced_count: number; total_players: number; missing_player_ids: number[]; missing_players: Missing[] }

export default function CoverageDrawer({ season, coveragePct, priced, total }: { season: number; coveragePct: number; priced: number; total: number }) {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<Coverage | null>(null)
  const [q, setQ] = useState('')

  useEffect(() => {
    if (!open) return
    fetch(`${API}/api/coverage?season=${season}`).then(r => r.json()).then(setData).catch(() => setData(null))
  }, [open, season])

  const filtered = data?.missing_players.filter(p => !q || p.name.toLowerCase().includes(q.toLowerCase()) || p.team.toLowerCase().includes(q.toLowerCase())) ?? []

  return (
    <>
      <button type="button" className="coverage-trigger" onClick={() => setOpen(v => !v)} aria-expanded={open}>
        {open ? 'Hide missing' : `View ${total - priced} missing`} →
      </button>
      {open && (
        <div className="coverage-drawer">
          <div className="coverage-drawer-head">
            <strong>{data ? `${filtered.length} of ${data.missing_player_ids.length} missing` : 'Loading…'}</strong>
            <span>{coveragePct}% priced · {priced}/{total}</span>
          </div>
          <input placeholder="Filter missing — name or team" value={q} onChange={e => setQ(e.target.value)} className="coverage-filter" />
          <div className="coverage-list">
            {filtered.slice(0, 80).map(p => (
              <div key={p.id} className="coverage-row">
                <span><strong>{p.name}</strong><small>{p.team} · {p.primary_position} · #{p.id}</small></span>
                <span className="coverage-badge">no salary</span>
              </div>
            ))}
            {filtered.length > 80 && <div className="coverage-more">+{filtered.length - 80} more — refine filter or download template</div>}
            {filtered.length === 0 && data && <div className="coverage-empty">No missing players match “{q}”.</div>}
          </div>
          <div className="coverage-actions">
            <a className="template-link" href={`${API}/api/salaries/template?season=${season}`} download>Download template CSV</a>
            <span className="coverage-help">Add source_url + checked_at to include a player in optimization.</span>
          </div>
        </div>
      )}
    </>
  )
}
