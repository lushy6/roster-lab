import { useEffect, useState } from 'react'
import { buildScenario, getStatus, importSalaries, refreshMlb, seedDemo, type Scenario, type Status } from './api'
import ScenarioForm from './components/ScenarioForm'
import RosterView from './components/RosterView'
import SourceDetails from './components/SourceDetails'
import './style.css'

function ids(value: string): number[] {
  if (!value.trim()) return []
  const parts = value.split(',').map(part => Number(part.trim()))
  if (parts.some(part => !Number.isInteger(part) || part <= 0)) throw new Error('Player IDs must be positive numbers separated by commas.')
  return parts
}

export default function App() {
  const [season, setSeason] = useState(2026)
  const [cap, setCap] = useState('150')
  const [locked, setLocked] = useState('')
  const [excluded, setExcluded] = useState('')
  const [status, setStatus] = useState<Status | null>(null)
  const [scenario, setScenario] = useState<Scenario | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  async function reloadStatus(selectedSeason = season) {
    try { setStatus(await getStatus(selectedSeason)) } catch { setMessage('The local API is unavailable. Start the backend and reload this page.') }
  }
  useEffect(() => { void reloadStatus(season) }, [season])

  async function action(work: () => Promise<unknown>, success: string) {
    setBusy(true); setMessage('')
    try { await work(); await reloadStatus(); setMessage(success) }
    catch (error) { setMessage(error instanceof Error ? error.message : 'The action failed.') }
    finally { setBusy(false) }
  }

  async function build() {
    const amount = Number(cap)
    if (!Number.isFinite(amount) || amount <= 0) { setMessage('Enter a payroll limit above zero.'); return }
    setBusy(true); setMessage('')
    try { setScenario(await buildScenario(season, Math.round(amount * 1_000_000), ids(locked), ids(excluded))) }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Could not build a roster.') }
    finally { setBusy(false) }
  }

  async function upload(file: File | undefined) {
    if (!file) return
    setBusy(true); setMessage('')
    try {
      const result = await importSalaries(season, await file.text())
      await reloadStatus()
      setMessage(`Imported ${result.accepted} salaries; ${result.issues.length} rows need review.`)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Salary import failed.') }
    finally { setBusy(false) }
  }

  return <><header className="site-header"><div className="header-inner"><a className="brand" href="/"><span className="brand-mark" aria-hidden="true">◆</span><span>Roster Lab</span></a><span className="header-side">A baseball front office sandbox</span></div></header>
    <main className="page-shell"><div className="lead"><div><p className="lead-kicker">The roster is a decision.</p><h1>Build the team<br />you can afford.</h1><p className="lead-copy">Set the payroll. Fill every role. See which players make the most of your money.</p></div><div className="lead-aside"><span className="aside-diamond" aria-hidden="true">◇</span><p>26 players<br />One payroll<br />Every choice counts</p></div></div>
      <div className="workspace"><aside className="controls"><ScenarioForm season={season} cap={cap} locked={locked} excluded={excluded} busy={busy} onSeason={setSeason} onCap={setCap} onLocked={setLocked} onExcluded={setExcluded} onBuild={() => void build()} />
        <section className="data-panel"><h2>Player data</h2><p className="data-state">{status?.players ? `${status.priced_players} of ${status.players} players have salaries` : 'No player data loaded'}</p>{status?.snapshot_at && <p className="data-date">Updated {new Date(status.snapshot_at).toLocaleString()}</p>}{status?.is_demo && <p className="demo-tag">Fictional demo data</p>}
          <div className="data-actions"><button type="button" onClick={() => void action(seedDemo, 'Fictional demo data loaded.')} disabled={busy}>Try demo data</button><button type="button" onClick={() => void action(() => refreshMlb(season), 'Live MLB players refreshed. Import salaries to build a real-player roster.')} disabled={busy}>Refresh MLB players</button>{status?.players ? <a className="template-link" href={`http://127.0.0.1:8000/api/salaries/template?season=${season}`} download>Download player template</a> : null}<label className="upload-button">Import salary CSV<input aria-label="Import salary CSV" type="file" accept=".csv,text/csv" onChange={event => void upload(event.target.files?.[0])} /></label></div>
          <p className="data-help">Real-player rosters need an attributed salary CSV. Players without a salary are excluded.</p></section>
      </aside><div className="results" aria-live="polite">{message && <div className="message" role="status">{message}</div>}{scenario ? <><RosterView scenario={scenario} /><SourceDetails scenario={scenario} /></> : <section className="empty-result"><span className="empty-diamond" aria-hidden="true">◇</span><h2>Your roster starts here.</h2><p>Load demo data or refresh MLB players and import salaries. Then set a limit and build your roster.</p><div className="empty-rule" /></section>}</div></div>
    </main><footer className="site-footer"><span>Roster Lab</span><span>Scenario cap and player values are estimates, not MLB rules or official projections.</span></footer></>
}
