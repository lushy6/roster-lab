import type { Pick, Scenario } from '../api'

const money = (value: number) => `$${(value / 1_000_000).toFixed(1)}m`
const groups = [
  { title: 'Starting lineup', test: (slot: string) => !slot.startsWith('SP') && !slot.startsWith('RP') && !slot.startsWith('BN') && slot !== 'C2' },
  { title: 'Bench', test: (slot: string) => slot.startsWith('BN') || slot === 'C2' },
  { title: 'Rotation', test: (slot: string) => slot.startsWith('SP') },
  { title: 'Bullpen', test: (slot: string) => slot.startsWith('RP') },
]

function PlayerRow({ pick }: { pick: Pick }) { return <div className="player-row" data-testid="roster-player"><span className="slot">{pick.slot}</span><div className="player-name"><strong>{pick.name}</strong><small>{pick.team} · {pick.input_seasons.join('–') || 'limited history'} · {pick.uncertainty} uncertainty</small></div><span className="player-war">{pick.war.toFixed(1)} <small>est. WAR</small></span><span className="player-salary">{money(pick.salary)}</span></div> }

export default function RosterView({ scenario }: { scenario: Scenario }) {
  const roster = scenario.roster
  return <section className="roster-section">
    <div className="roster-heading"><div><h2>Your 26-player roster</h2><p>One player per role, under your payroll limit.</p></div><span className="status-pill">{roster.status === 'optimal' ? 'Proven optimum' : 'Valid result'}</span></div>
    <div className="scoreline"><div><span>Payroll</span><strong>{money(roster.total_salary)}</strong><small>of {money(scenario.cap_usd)} limit</small></div><div><span>Cap remaining</span><strong>{money(scenario.cap_usd - roster.total_salary)}</strong><small>room for changes</small></div><div><span>Projected value</span><strong>{roster.total_war.toFixed(1)}</strong><small>estimated WAR</small></div></div>
    <div className="roster-groups">{groups.map(group => <div className="roster-group" key={group.title}><h3>{group.title}</h3><div className="player-list">{roster.picks.filter(p => group.test(p.slot)).map(pick => <PlayerRow pick={pick} key={pick.slot} />)}</div></div>)}</div>
    {scenario.alternatives.length > 0 && <div className="compare"><h3>Compare budgets</h3><div className="compare-list">{scenario.alternatives.map(alt => <div className="compare-item" key={alt.cap_usd}><span>{money(alt.cap_usd)} limit</span><strong>{alt.roster.total_war.toFixed(1)} estimated WAR</strong><small>{money(alt.roster.total_salary)} payroll</small></div>)}</div></div>}
  </section>
}
