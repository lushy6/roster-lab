import type { FormEvent } from 'react'

type Props = { season: number; cap: string; locked: string; excluded: string; busy: boolean; onSeason: (n: number) => void; onCap: (s: string) => void; onLocked: (s: string) => void; onExcluded: (s: string) => void; onBuild: () => void }

export default function ScenarioForm(p: Props) {
  const submit = (event: FormEvent) => { event.preventDefault(); p.onBuild() }
  return <form className="scenario-form" onSubmit={submit}>
    <div className="form-intro"><span className="field-mark" aria-hidden="true">◇</span><div><h2>Set the terms</h2><p>Choose a payroll limit. We fill every roster role within it.</p></div></div>
    <div className="field-grid">
      <label>Payroll limit <span className="input-wrap"><span>$</span><input aria-label="Payroll limit" type="number" min="1" step="1" value={p.cap} onChange={event => p.onCap(event.target.value)} /><span>million</span></span></label>
      <label>Season <select value={p.season} onChange={event => p.onSeason(Number(event.target.value))}><option value={2026}>2026</option><option value={2025}>2025</option><option value={2024}>2024</option></select></label>
    </div>
    <details className="advanced"><summary>Player rules</summary><p>Use MLB player IDs, separated by commas.</p><div className="field-grid"><label>Lock players<input value={p.locked} onChange={event => p.onLocked(event.target.value)} placeholder="e.g. 592450" /></label><label>Exclude players<input value={p.excluded} onChange={event => p.onExcluded(event.target.value)} placeholder="e.g. 605141" /></label></div></details>
    <button className="primary-button" disabled={p.busy} type="submit">{p.busy ? 'Building roster…' : 'Build roster'}</button>
  </form>
}
