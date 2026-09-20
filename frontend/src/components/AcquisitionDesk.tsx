import type { Scenario } from '../api'

export default function AcquisitionDesk({ scenario }: { scenario: Scenario }) {
  const priced = new Set(scenario.roster.picks.map(p=>p.player_id))
  const capRoom = scenario.cap_usd - scenario.roster.total_salary
  return (
    <section className="acquisition-desk">
      <h3>Acquisition desk — market view</h3>
      <p className="acquisition-help">Team control & trade feasibility (Phase 3). For now: hypothetical availability — every priced player is considered available. Cap room <strong>${(capRoom/1_000_000).toFixed(1)}m</strong>.</p>
      <div className="acquisition-grid">
        <div className="acq-card"><h4>Free agents (mock)</h4><p>Would filter by {scenario.salary_coverage ? `${scenario.salary_coverage.priced_count} priced` : 'coverage'} pool. Coming: qualifying offers, control years.</p><span className="acq-pill">Phase 3</span></div>
        <div className="acq-card"><h4>Trade packages</h4><p>Validate {priced.size} rostered vs league-wide pool. Coming: surplus-value matching, 40-man constraints.</p><span className="acq-pill">Phase 3</span></div>
        <div className="acq-card is-highlight"><h4>Your leverage</h4><p>{capRoom > 0 ? `You can absorb $${(capRoom/1_000_000).toFixed(1)}m without shedding salary.` : 'Over cap — move salary to add.'} Efficiency {(scenario.roster.total_war/(scenario.roster.total_salary/1_000_000)).toFixed(2)} WAR/$1M.</p></div>
      </div>
    </section>
  )
}
