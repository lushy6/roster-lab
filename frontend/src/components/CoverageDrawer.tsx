import { useEffect, useState } from 'react'
import { getCoverage, salaryTemplateUrl, type Coverage } from '../api'

export default function CoverageDrawer({ season, coveragePct, priced, total }: { season: number; coveragePct: number; priced: number; total: number }) {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<Coverage | null>(null)
  const [error, setError] = useState('')
  const [q, setQ] = useState('')

  useEffect(() => {
    if (!open) return
    let cancelled = false
    getCoverage(season)
      .then(result => { if (!cancelled) { setData(result); setError('') } })
      .catch(reason => { if (!cancelled) { setData(null); setError(reason instanceof Error ? reason.message : 'Could not load coverage.') } })
    return () => { cancelled = true }
  }, [open, season, priced, total]) // refetch when an import changes the counts while the drawer is open

  const needle = q.toLowerCase()
  const filtered = data?.missing_players.filter(p => !needle || p.name.toLowerCase().includes(needle) || p.team.toLowerCase().includes(needle)) ?? []

  return (
    <>
      <button type="button" className="coverage-trigger" onClick={() => setOpen(v => !v)} aria-expanded={open}>
        {open ? 'Hide missing' : `View ${total - priced} missing`} →
      </button>
      {open && (
        <div className="coverage-drawer">
          <div className="coverage-drawer-head">
            <strong>{data ? `${filtered.length} of ${data.missing_player_ids.length} missing` : error ? 'Unavailable' : 'Loading…'}</strong>
            <span>{coveragePct}% priced · {priced}/{total}</span>
          </div>
          {error && <div className="coverage-empty" role="alert">{error}</div>}
          <input placeholder="Filter missing — name or team" aria-label="Filter missing players" value={q} onChange={e => setQ(e.target.value)} className="coverage-filter" />
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
            <a className="template-link" href={salaryTemplateUrl(season)} download>Download template CSV</a>
            <span className="coverage-help">Add source_url + checked_at to include a player in optimization.</span>
          </div>
        </div>
      )}
    </>
  )
}
