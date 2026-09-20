import { useEffect, useState } from 'react'
import { Toaster, toast } from 'sonner'
import { buildScenario, getScenario, getStatus, importSalaries, listScenarios, refreshMlb, seedDemo, type SavedScenario, type Scenario, type Status } from './api'
import ScenarioForm from './components/ScenarioForm'
import RosterView from './components/RosterView'
import SourceDetails from './components/SourceDetails'
import CoverageDrawer from './components/CoverageDrawer'
import DepthChart from './components/DepthChart'
import ContractDesk from './components/ContractDesk'
import AcquisitionDesk from './components/AcquisitionDesk'
import SeasonLab from './components/SeasonLab'
import './style.css'

export default function App() {
  const [season, setSeason] = useState(2026)
  const [cap, setCap] = useState('150')
  const [lockedIds, setLockedIds] = useState<number[]>([])
  const [excludedIds, setExcludedIds] = useState<number[]>([])
  const [status, setStatus] = useState<Status | null>(null)
  const [scenario, setScenario] = useState<Scenario | null>(null)
  const [savedScenarios, setSavedScenarios] = useState<SavedScenario[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [tab, setTab] = useState<'roster'|'depth'|'contracts'|'market'|'season'>('roster')

  async function reloadStatus(selectedSeason = season) {
    try {
      const [nextStatus, history] = await Promise.all([getStatus(selectedSeason), listScenarios(selectedSeason)])
      setStatus(nextStatus)
      setSavedScenarios(history)
    } catch {
      const msg = 'The local API is unavailable. Start the backend and reload.'
      setMessage(msg)
      toast.error(msg)
    }
  }
  useEffect(() => { setScenario(null); void reloadStatus(season) }, [season])

  async function action(work: () => Promise<unknown>, success: string) {
    setBusy(true); setMessage('')
    try { await work(); await reloadStatus(); setMessage(success); toast.success(success) }
    catch (error) { const msg = error instanceof Error ? error.message : 'The action failed.'; setMessage(msg); toast.error(msg) }
    finally { setBusy(false) }
  }

  async function build() {
    const amount = Number(cap)
    if (!Number.isFinite(amount) || amount <= 0) { const m='Enter a payroll limit above zero.'; setMessage(m); toast.error(m); return }
    if (lockedIds.some(id => excludedIds.includes(id))) { const m='A player cannot be both locked and excluded.'; setMessage(m); toast.error(m); return }
    setBusy(true); setMessage('')
    try {
      const result = await buildScenario(season, Math.round(amount * 1_000_000), lockedIds, excludedIds)
      setScenario(result)
      await reloadStatus()
      toast.success(`${result.roster.total_war.toFixed(1)} WAR for ${(result.roster.total_salary/1_000_000).toFixed(1)}m`)
    }
    catch (error) { const msg = error instanceof Error ? error.message : 'Could not build a roster.'; setMessage(msg); toast.error(msg) }
    finally { setBusy(false) }
  }

  async function upload(file: File | undefined) {
    if (!file) return
    setBusy(true); setMessage('')
    try {
      const result = await importSalaries(season, await file.text())
      await reloadStatus()
      const msg = `Imported ${result.accepted} salaries; ${result.issues.length} rows need review.`
      setMessage(msg); toast.success(msg)
    } catch (error) { const msg = error instanceof Error ? error.message : 'Salary import failed.'; setMessage(msg); toast.error(msg) }
    finally { setBusy(false) }
  }

  const coveragePct = status?.players ? Math.round((status.priced_players / status.players) * 100) : 0

  return <>
    <Toaster position="top-right" richColors closeButton theme="light" toastOptions={{ duration: 2600 }} />
    <header className="site-header">
      <div className="header-inner">
        <a className="brand" href="/"><span className="brand-mark" aria-hidden>◆</span><span>Roster Lab</span></a>
        <div className="header-nav">
          {status && <span className="header-pill">{status.priced_players} / {status.players} priced · {coveragePct}%</span>}
          <span className="header-side">A baseball front-office sandbox</span>
        </div>
      </div>
    </header>
    <main className="page-shell">
      <div className="lead">
        <div>
          <p className="lead-kicker">The roster is a decision.</p>
          <h1>Build the team<br />you can afford.</h1>
          <p className="lead-copy">Set the payroll. Fill every role. See which players make the most of your money — optimized for WAR per dollar, not just stars.</p>
        </div>
        <div className="lead-aside"><span className="aside-diamond" aria-hidden>◇</span><p>26 players<br />One payroll<br />Every choice counts</p></div>
      </div>
      <div className="workspace">
        <aside className="controls">
          <ScenarioForm season={season} cap={cap} lockedIds={lockedIds} excludedIds={excludedIds} busy={busy} onSeason={setSeason} onCap={setCap} onLockedIds={setLockedIds} onExcludedIds={setExcludedIds} onBuild={() => void build()} />
          <section className="data-panel card">
            <h2>Player data</h2>
            <p className="data-state">
              {status?.players ? <><strong>{status.priced_players}</strong> of <strong>{status.players}</strong> players have salaries</> : 'No player data loaded'}
            </p>
            {status?.players ? <><div className="coverage-bar" aria-hidden><div className="coverage-fill" style={{ width: `${coveragePct}%` }} /></div><CoverageDrawer season={season} coveragePct={coveragePct} priced={status.priced_players} total={status.players} /></> : null}
            {status?.snapshot_at && <p className="data-date">Updated {new Date(status.snapshot_at).toLocaleString()}</p>}
            {status?.is_demo && <p className="demo-tag">Fictional demo data</p>}
            <div className="data-actions">
              <button type="button" onClick={() => void action(seedDemo, 'Fictional demo data loaded.')} disabled={busy}>Try demo data</button>
              <button type="button" onClick={() => void action(() => refreshMlb(season), 'Live MLB players refreshed. Import salaries to build a real-player roster.')} disabled={busy}>Refresh MLB players</button>
              {status?.players ? <a className="template-link" href={`http://127.0.0.1:8000/api/salaries/template?season=${season}`} download>Download player template</a> : null}
              <label className="upload-button">Import salary CSV<input aria-label="Import salary CSV" type="file" accept=".csv,text/csv" onChange={event => void upload(event.target.files?.[0])} /></label>
            </div>
            <p className="data-help">Real-player rosters need an attributed salary CSV. Players without a salary are excluded and shown in the coverage report.</p>
            {savedScenarios.length > 0 && (
              <div className="history">
                <h3>Saved scenarios</h3>
                <div className="history-list">
                  {savedScenarios.map(saved => (
                    <button type="button" className="history-button" key={saved.id} disabled={busy} onClick={() => { setBusy(true); void getScenario(saved.id).then(s => { setScenario(s); toast.success('Scenario reopened') }).catch(() => { const m='Could not reopen that scenario.'; setMessage(m); toast.error(m) }).finally(() => setBusy(false)) }}>
                      <span>{saved.is_demo ? 'Demo' : 'Scenario'} · {new Date(saved.created_at).toLocaleDateString()}</span>
                      <strong>{saved.total_war.toFixed(1)} WAR</strong>
                      <small>{(saved.cap_usd / 1_000_000).toFixed(0)}m cap · {(saved.total_salary / 1_000_000).toFixed(1)}m payroll</small>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </section>
        </aside>
        <div className="results" aria-live="polite">
          {message && <div className="message" role="status">{message}</div>}
          {busy && !scenario && (
            <section className="roster-section" aria-hidden>
              <div className="roster-heading"><div><div className="skeleton" style={{ width: 200, height: 28 }} /><div className="skeleton" style={{ width: 260, height: 14, marginTop: 8 }} /></div><span className="skeleton" style={{ width: 110, height: 26, borderRadius: 999 }} /></div>
              <div className="scoreline"><div className="skeleton" style={{ height: 72 }} /><div className="skeleton" style={{ height: 72 }} /><div className="skeleton" style={{ height: 72 }} /><div className="skeleton" style={{ height: 72 }} /></div>
            </section>
          )}
          {scenario ? <>
            <div className="roster-tabs" role="tablist">
              {(['roster','depth','contracts','market','season'] as const).map(t=>(
                <button key={t} role="tab" aria-selected={tab===t} className={`roster-tab ${tab===t?'is-active':''}`} onClick={()=>setTab(t)}>
                  {t==='roster'?'Roster':t==='depth'?'Depth chart':t==='contracts'?'Contracts':t==='market'?'Market':'Season lab'}
                </button>
              ))}
            </div>
            {tab==='roster' && <RosterView scenario={scenario} />}
            {tab==='depth' && <DepthChart scenario={scenario} />}
            {tab==='contracts' && <ContractDesk scenario={scenario} />}
            {tab==='market' && <AcquisitionDesk scenario={scenario} />}
            {tab==='season' && <SeasonLab scenario={scenario} />}
            <SourceDetails scenario={scenario} />
          </> : !busy && (
            <section className="empty-result">
              <span className="empty-diamond" aria-hidden>◇</span>
              <h2>Your roster starts here.</h2>
              <p>Load demo data or refresh MLB players and import salaries. Then set a limit and build your roster — every role filled, every dollar counted.</p>
              <div className="empty-rule" />
            </section>
          )}
        </div>
      </div>
    </main>
    <footer className="site-footer"><span>Roster Lab</span><span>Scenario cap and player values are estimates, not MLB rules or official projections.</span></footer>
  </>
}
