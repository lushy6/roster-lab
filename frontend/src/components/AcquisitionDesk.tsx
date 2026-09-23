import type { Scenario } from '../api'

export default function AcquisitionDesk({ scenario }: { scenario: Scenario }) {
  const rostered = scenario.roster.picks.length
  const capRoom = scenario.cap_usd - scenario.roster.total_salary
  const salary = scenario.roster.total_salary
  const efficiency = salary > 0 ? (scenario.roster.total_war / (salary / 1_000_000)).toFixed(2) : '—'
  return (
    <section className="acquisition-desk">
      <h3>Market <span className="acq-pill">Preview</span></h3>
      <p className="acquisition-help">Every priced player is treated as available to you. Free agency and trades are not modelled yet. Cap room: <strong>${(capRoom / 1_000_000).toFixed(1)}m</strong>.</p>
      <div className="acquisition-grid">
        <div className="acq-card"><h4>Free agents</h4><p>Not built yet. It would draw on the {scenario.salary_coverage ? `${scenario.salary_coverage.priced_count} priced players` : 'priced pool'}, with qualifying offers and control years.</p><span className="acq-pill">Coming later</span></div>
        <div className="acq-card"><h4>Trade packages</h4><p>Not built yet. It would weigh your {rostered} rostered players against the league-wide pool, with surplus-value matching and 40-man limits.</p><span className="acq-pill">Coming later</span></div>
        <div className="acq-card is-highlight"><h4>Your leverage</h4><p>{capRoom > 0 ? `You can absorb $${(capRoom / 1_000_000).toFixed(1)}m without shedding salary.` : 'At or over the limit: move salary to add anyone.'} Efficiency {efficiency} WAR/$1M.</p></div>
      </div>
    </section>
  )
}
