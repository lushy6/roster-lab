import type { Scenario } from '../api'

const millions = (value: number) => `$${(value / 1_000_000).toFixed(1)}m`

export default function ContractDesk({ scenario }: { scenario: Scenario }) {
  const { season, roster } = scenario
  return (
    <section className="contract-desk">
      <h3>Contract desk <span className="acq-pill">Preview</span></h3>
      <p className="contract-help">The {season} column is each player's salary from your register. Later years only repeat that figure: options, arbitration and real contract lengths are not loaded yet, so treat the starred columns as placeholders.</p>
      <div className="contract-table-wrap">
        <table className="contract-table">
          <thead><tr><th>Player</th><th>Slot</th><th>{season}</th><th>{season + 1} *</th><th>{season + 2} *</th><th>Total 3yr *</th></tr></thead>
          <tbody>
            {roster.picks.map(p => (
              <tr key={p.player_id}>
                <td>{p.name}</td><td>{p.slot}</td><td>{millions(p.salary)}</td>
                <td className="is-est">~{millions(p.salary)}</td><td className="is-est">~{millions(p.salary)}</td>
                <td><strong>{millions(p.salary * 3)}</strong></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="contract-foot">* Placeholder: the {season} salary carried forward unchanged.</p>
    </section>
  )
}
