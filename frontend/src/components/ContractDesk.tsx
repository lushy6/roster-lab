import type { Scenario } from '../api'

export default function ContractDesk({ scenario }: { scenario: Scenario }) {
  // Roadmap Phase 2 stub — multi-year view mocked from base salary
  return (
    <section className="contract-desk">
      <h3>Contract desk — multi-year commitments</h3>
      <p className="contract-help">Base salary from {scenario.season} register. Options/arbitration estimates arrive in Phase 2 — this table shows 3-year carry-forward at flat rate with {((scenario.roster.total_salary/scenario.cap_usd)*100).toFixed(0)}% cap hold.</p>
      <div className="contract-table-wrap">
        <table className="contract-table">
          <thead><tr><th>Player</th><th>Pos</th><th>{scenario.season}</th><th>{scenario.season+1} *</th><th>{scenario.season+2} *</th><th>Total 3yr</th></tr></thead>
          <tbody>
            {scenario.roster.picks.slice(0,8).map(p=>(
              <tr key={p.player_id}><td>{p.name}</td><td>{p.slot}</td><td>${(p.salary/1_000_000).toFixed(1)}m</td><td className="is-est">~${(p.salary/1_000_000).toFixed(1)}m</td><td className="is-est">~${(p.salary/1_000_000).toFixed(1)}m</td><td><strong>${((p.salary*3)/1_000_000).toFixed(1)}m</strong></td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="contract-foot">* Estimates — flat carry. Licensed feed will replace with real arbitration/option terms. Remaining {scenario.roster.picks.length - 8} players hidden.</p>
    </section>
  )
}
