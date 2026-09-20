import type { Pick, Scenario } from '../api'
import LineupGraphic from './LineupGraphic'

const money = (value: number) => `$${(value / 1_000_000).toFixed(1)}m`
const warPerMillion = (war: number, salary: number) => salary > 0 ? (war / (salary / 1_000_000)).toFixed(2) : '—'
const groups = [
  { title: 'Bench', test: (slot: string) => slot.startsWith('BN') || slot === 'C2' },
  { title: 'Rotation', test: (slot: string) => slot.startsWith('SP') },
  { title: 'Bullpen', test: (slot: string) => slot.startsWith('RP') },
]

function PlayerRow({ pick, index }: { pick: Pick; index: number }) {
  const uncColor = pick.uncertainty === 'high' ? '#c4363f' : pick.uncertainty === 'medium' ? '#b07a00' : '#5f7683'
  const s = pick.stats || {}
  const statText = s.era ? `${s.era} ERA · ${s.ip} IP` : s.ops ? `${s.avg ? Number(s.avg).toFixed(3).replace(/^0/,'') : '—'} · ${s.ops ? Number(s.ops).toFixed(3) : '—'} OPS · ${s.hr ?? '—'} HR` : ''
  return (
    <div className="player-row" data-testid="roster-player" style={{ animationDelay: `${index * 28}ms` }}>
      <span className="slot">{pick.slot}</span>
      <div className="player-name">
        <strong>{pick.name} <span className="eff-badge" title="WAR per $1M">{warPerMillion(pick.war, pick.salary)}/$1M</span></strong>
        <small>{pick.team_abbrev || pick.team} · {statText} {statText ? '·' : ''} {pick.input_seasons.join('–') || 'limited'} · <span className="unc-dot" style={{ background: uncColor }} />{pick.uncertainty}</small>
      </div>
      <span className="player-war" title={`Hitting ${pick.hitting_war.toFixed(1)} + Pitching ${pick.pitching_war.toFixed(1)}`}>{pick.war.toFixed(1)} <small>est. WAR</small></span>
      <span className="player-salary">{money(pick.salary)}</span>
    </div>
  )
}

function exportCsv(scenario: Scenario) {
  const rows = [['slot','player_id','name','team','salary_usd','war','uncertainty','source_url']]
  for (const p of scenario.roster.picks) rows.push([p.slot, String(p.player_id), `"${p.name}"`, p.team, String(p.salary), p.war.toFixed(2), p.uncertainty, p.salary_source_url])
  const csv = rows.map(r => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `roster-${scenario.season}-${scenario.cap_usd}.csv`; a.click()
  URL.revokeObjectURL(url)
}

export default function RosterView({ scenario }: { scenario: Scenario }) {
  const roster = scenario.roster
  const efficiency = roster.total_salary > 0 ? (roster.total_war / (roster.total_salary / 1_000_000)).toFixed(2) : '—'
  const pct = Math.min(100, Math.round((roster.total_salary / scenario.cap_usd) * 100))
  let idx = 0
  const gaugeColor = pct > 95 ? '#c4363f' : pct > 85 ? '#d98a1a' : '#1f9d6a'
  const primaryIds = new Set(roster.picks.map(p => p.player_id))
  return (
    <section className="roster-section">
      <div className="roster-heading">
        <div>
          <h2>Your 26-player roster</h2>
          <p>One player per role, under your payroll limit. {pct}% of cap used · {efficiency} WAR/$1M</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button type="button" className="template-link" onClick={() => exportCsv(scenario)} style={{ padding: '6px 10px', fontSize: 12 }}>Export CSV</button>
          <span className="status-pill">{roster.status === 'optimal' ? 'Proven optimum' : 'Valid result'}</span>
        </div>
      </div>
      <div className="scoreline">
        <div><span>Payroll</span><strong>{money(roster.total_salary)}</strong><small>of {money(scenario.cap_usd)} limit</small></div>
        <div><span>Cap remaining</span><strong>{money(scenario.cap_usd - roster.total_salary)}</strong><small>{pct}% utilized</small></div>
        <div><span>Projected value</span><strong>{roster.total_war.toFixed(1)}</strong><small>estimated WAR</small></div>
        <div><span>Efficiency</span><strong>{efficiency}</strong><small>WAR per $1M</small></div>
      </div>
      <div className="payroll-gauge" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Payroll utilization">
        <div className="payroll-gauge-track"><div className="payroll-gauge-fill" style={{ width: `${pct}%`, background: gaugeColor }} /></div>
        <span style={{ color: gaugeColor }}>{pct}% cap · {money(scenario.cap_usd - roster.total_salary)} remaining</span>
      </div>
      <LineupGraphic picks={roster.picks} />
      <div className="roster-groups">
        {groups.map(group => (
          <div className="roster-group" key={group.title}>
            <h3>{group.title} <small style={{ fontFamily: 'DM Sans', fontWeight: 500, color: '#6b8794', marginLeft: 6 }}>{roster.picks.filter(p=>group.test(p.slot)).length} players</small></h3>
            <div className="player-list">
              {roster.picks.filter(p => group.test(p.slot)).map(pick => <PlayerRow pick={pick} key={pick.slot} index={idx++} />)}
            </div>
          </div>
        ))}
      </div>
      {scenario.alternatives.length > 0 && (
        <div className="compare">
          <h3>Compare budgets</h3>
          <div className="compare-list">
            {scenario.alternatives.map(alt => {
              const newCount = alt.roster.picks.filter(p => !primaryIds.has(p.player_id)).length
              return (
                <div className="compare-item" key={alt.cap_usd}>
                  <span>{money(alt.cap_usd)} limit {alt.distinct_from_primary ? '· distinct' : ''}</span>
                  <strong>{alt.roster.total_war.toFixed(1)} estimated WAR</strong>
                  <small>{money(alt.roster.total_salary)} payroll · {(alt.roster.total_war / (alt.roster.total_salary / 1_000_000)).toFixed(2)} WAR/$1M</small>
                  <small style={{ color: newCount ? '#1a5a7a' : '#6b8794', fontWeight: 600 }}>{newCount ? `${newCount} new players vs primary` : 'Same core'}</small>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </section>
  )
}
