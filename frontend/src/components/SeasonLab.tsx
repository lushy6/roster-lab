import { useState } from 'react'
import type { Scenario } from '../api'

export default function SeasonLab({ scenario }: { scenario: Scenario }) {
  const [variance, setVariance] = useState(12)
  const base = scenario.roster.total_war
  const low = (base * (1 - variance / 100)).toFixed(1)
  const high = (base * (1 + variance / 100)).toFixed(1)
  return (
    <section className="season-lab">
      <h3>Season lab <span className="acq-pill">Preview</span></h3>
      <p className="season-help">Illustrative only. The slider widens or narrows a band around the roster's {base.toFixed(1)} estimated WAR. It is not simulated from playing-time or injury data, so it says nothing about how likely any outcome is.</p>
      <div className="season-controls">
        <label>Band width <input type="range" min={5} max={30} value={variance} onChange={e => setVariance(Number(e.target.value))} /> ±{variance}%</label>
        <span className="season-band">{low} — {high} WAR</span>
      </div>
      <div className="season-bar">
        <div className="season-bar-track"><div className="season-bar-fill" style={{ left: `${50 - variance / 2}%`, width: `${variance}%` }} /></div>
        <div className="season-labels"><span>{low}</span><strong>{base.toFixed(1)} base</strong><span>{high}</span></div>
      </div>
      <p className="season-foot">Not built yet: a season simulation with playing-time and injury draws.</p>
    </section>
  )
}
