import { useState } from 'react'
import type { Scenario } from '../api'

export default function SeasonLab({ scenario }: { scenario: Scenario }) {
  const [variance, setVariance] = useState(12)
  const base = scenario.roster.total_war
  const low = (base * (1 - variance/100)).toFixed(1)
  const high = (base * (1 + variance/100)).toFixed(1)
  return (
    <section className="season-lab">
      <h3>Season lab — outcome uncertainty</h3>
      <p className="season-help">Playing-time & injury variance (Phase 4). {base.toFixed(1)} WAR base — showing ±{variance}% band as proxy for simulation.</p>
      <div className="season-controls">
        <label>Variance <input type="range" min={5} max={30} value={variance} onChange={e=>setVariance(Number(e.target.value))} /> {variance}%</label>
        <span className="season-band">{low} — {high} WAR</span>
      </div>
      <div className="season-bar">
        <div className="season-bar-track"><div className="season-bar-fill" style={{ left: `${50 - variance/2}%`, width: `${variance}%` }} /></div>
        <div className="season-labels"><span>{low}</span><strong>{base.toFixed(1)} base</strong><span>{high}</span></div>
      </div>
      <p className="season-foot">Future: Monte Carlo with playing-time allocation, IL risk, and playoff odds from repeated draws. Deterministic now.</p>
    </section>
  )
}
