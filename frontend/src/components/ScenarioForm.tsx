import type { FormEvent } from 'react'
import PlayerPicker from './PlayerPicker'

type Props = {
  season: number
  seasons: number[]
  cap: string
  lockedIds: number[]
  excludedIds: number[]
  busy: boolean
  onSeason: (n: number) => void
  onCap: (s: string) => void
  onLockedIds: (ids: number[]) => void
  onExcludedIds: (ids: number[]) => void
  onBuild: () => void
}

export default function ScenarioForm(p: Props) {
  const submit = (event: FormEvent) => { event.preventDefault(); p.onBuild() }
  return (
    <form className="scenario-form" onSubmit={submit}>
      <div className="form-intro"><span className="field-mark" aria-hidden>◇</span><div><h2>Set the terms</h2><p>Choose a payroll limit. We fill every roster role within it.</p></div></div>
      <div className="field-grid">
        <label>Payroll limit <span className="input-wrap"><span>$</span><input aria-label="Payroll limit" type="number" min="1" step="1" value={p.cap} onChange={event => p.onCap(event.target.value)} /><span>million</span></span></label>
        <label>Season <select value={p.season} onChange={event => p.onSeason(Number(event.target.value))}>{p.seasons.map(year => <option key={year} value={year}>{year}</option>)}</select></label>
      </div>
      <details className="advanced" open>
        <summary>Player rules</summary>
        <p>Search by name, team or ID. Priced players are preferred — unpriced can’t be optimized.</p>
        <div className="field-grid" style={{ gap: 16, marginTop: 12 }}>
          <PlayerPicker label="Lock players" placeholder="Search to lock — e.g. Ohtani" season={p.season} values={p.lockedIds} onChange={p.onLockedIds} disabled={p.busy} />
          <PlayerPicker label="Exclude players" placeholder="Search to exclude — e.g. Judge" season={p.season} values={p.excludedIds} onChange={p.onExcludedIds} disabled={p.busy} />
        </div>
      </details>
      <button className="primary-button" disabled={p.busy} type="submit">{p.busy ? 'Building roster…' : 'Build roster'}</button>
    </form>
  )
}
