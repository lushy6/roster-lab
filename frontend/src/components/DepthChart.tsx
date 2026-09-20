import type { Scenario } from '../api'

export default function DepthChart({ scenario }: { scenario: Scenario }) {
  const bySlot: Record<string, typeof scenario.roster.picks[0] | undefined> = {}
  for (const p of scenario.roster.picks) bySlot[p.slot] = p
  const order = ['C','1B','2B','3B','SS','LF','CF','RF','DH']
  return (
    <section className="depth-chart">
      <h3>Depth chart — field view</h3>
      <p className="depth-help">Diamond positions from your optimized roster. Bench and pitching below.</p>
      <div className="diamond">
        {order.map(pos => {
          const p = scenario.roster.picks.find(x => x.slot === pos)
          return <div key={pos} className={`diamond-pos pos-${pos.toLowerCase()}`}>
            <span className="diamond-label">{pos}</span>
            <strong>{p ? p.name : '—'}</strong>
            <small>{p ? `${p.team} · ${p.war.toFixed(1)} WAR` : 'vacant'}</small>
          </div>
        })}
      </div>
      <div className="depth-groups">
        <div><h4>Bench</h4><div className="depth-list">{scenario.roster.picks.filter(p=>p.slot.startsWith('BN')||p.slot==='C2').map(p=><span key={p.slot} className="depth-pill">{p.slot}: {p.name} <em>{p.war.toFixed(1)}</em></span>)}</div></div>
        <div><h4>Rotation</h4><div className="depth-list">{scenario.roster.picks.filter(p=>p.slot.startsWith('SP')).map(p=><span key={p.slot} className="depth-pill">{p.slot}: {p.name} <em>{p.war.toFixed(1)}</em></span>)}</div></div>
        <div><h4>Bullpen</h4><div className="depth-list">{scenario.roster.picks.filter(p=>p.slot.startsWith('RP')).map(p=><span key={p.slot} className="depth-pill">{p.slot}: {p.name} <em>{p.war.toFixed(1)}</em></span>)}</div></div>
      </div>
    </section>
  )
}
