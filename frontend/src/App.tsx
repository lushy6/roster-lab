import { useCallback, useEffect, useRef, useState } from 'react'
import { Toaster, toast } from 'sonner'
import { buildScenario, deleteScenario, exitDemo, getAccount, getScenario, getSeasons, getStatus, importSalaries, listScenarios, refreshMlb, salaryTemplateUrl, seedDemo, type Account, type SavedScenario, type Scenario, type Status } from './api'
import AccountPanel from './components/AccountPanel'
import ScenarioForm from './components/ScenarioForm'
import RosterView, { AlternativesAnnouncer } from './components/RosterView'
import SourceDetails from './components/SourceDetails'
import CoverageDrawer from './components/CoverageDrawer'
import DepthChart from './components/DepthChart'
import ContractDesk from './components/ContractDesk'
import AcquisitionDesk from './components/AcquisitionDesk'
import SeasonLab from './components/SeasonLab'
import './style.css'

export default function App() {
  const [season, setSeason] = useState(2026)
  const [seasons, setSeasons] = useState<number[]>([2026])
  const [cap, setCap] = useState('150')
  const [lockedIds, setLockedIds] = useState<number[]>([])
  const [excludedIds, setExcludedIds] = useState<number[]>([])
  const [status, setStatus] = useState<Status | null>(null)
  const [scenario, setScenario] = useState<Scenario | null>(null)
  const [savedScenarios, setSavedScenarios] = useState<SavedScenario[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [tab, setTab] = useState<'roster'|'depth'|'contracts'|'market'|'season'>('roster')
  const [account, setAccount] = useState<Account | null>(null)
  const [mineOnly, setMineOnly] = useState(false)

  // What the user is looking at right now, for async work that started earlier.
  const seasonRef = useRef(season)
  useEffect(() => { seasonRef.current = season }, [season])
  const latestReload = useRef(0)
  const mineRef = useRef(false)
  useEffect(() => { mineRef.current = mineOnly && account !== null }, [mineOnly, account])

  /** Loads status, saved scenarios and seasons. Only the newest call may update the screen; resolves false on failure. */
  const reloadStatus = useCallback(async (selectedSeason: number): Promise<boolean> => {
    const id = ++latestReload.current
    try {
      const [nextStatus, history, available] = await Promise.all([getStatus(selectedSeason), listScenarios(selectedSeason, mineRef.current), getSeasons()])
      if (id !== latestReload.current) return true
      setStatus(nextStatus)
      setSavedScenarios(history)
      setSeasons(available.length ? available : [2026])
      return true
    } catch {
      if (id === latestReload.current) {
        const msg = 'The local API is unavailable. Start the backend and reload.'
        setMessage(msg)
        toast.error(msg)
      }
      return false
    }
  }, [])
  useEffect(() => { setScenario(null); void reloadStatus(season) }, [season, reloadStatus])
  useEffect(() => { void getAccount().then(setAccount).catch(() => setAccount(null)) }, [])
  useEffect(() => { void reloadStatus(seasonRef.current) }, [mineOnly, account, reloadStatus])

  function onAccountChange(next: Account | null) {
    setAccount(next)
    if (!next) { setMineOnly(false); setScenario(null) } // a private roster must not stay on screen after sign-out
    toast.success(next ? `Signed in as ${next.email}` : 'Signed out')
  }

  async function removeScenario(saved: SavedScenario) {
    if (!window.confirm(`Delete the scenario from ${new Date(saved.created_at).toLocaleString()}? This cannot be undone.`)) return
    await action(async () => {
      await deleteScenario(saved.id)
      setScenario(current => (current?.id === saved.id ? null : current))
    }, 'Scenario deleted.')
  }

  // Locked and excluded ids only mean something for the data they were picked from.
  const isDemo = status?.is_demo ?? false
  useEffect(() => { setLockedIds([]); setExcludedIds([]) }, [season, isDemo])

  // The selected season must always be a choice, even before it has salaries.
  const seasonChoices = seasons.includes(season) ? seasons : [season, ...seasons].sort((a, b) => b - a)

  async function action(work: () => Promise<unknown>, success: string) {
    setBusy(true); setMessage('')
    try {
      await work()
      if (await reloadStatus(seasonRef.current)) { setMessage(success); toast.success(success) }
    }
    catch (error) { const msg = error instanceof Error ? error.message : 'The action failed.'; setMessage(msg); toast.error(msg) }
    finally { setBusy(false) }
  }

  async function build() {
    const amount = Number(cap)
    if (!Number.isFinite(amount) || amount <= 0) { const m='Enter a payroll limit above zero.'; setMessage(m); toast.error(m); return }
    if (lockedIds.some(id => excludedIds.includes(id))) { const m='A player cannot be both locked and excluded.'; setMessage(m); toast.error(m); return }
    const requestedSeason = season
    setBusy(true); setMessage('')
    try {
      const result = await buildScenario(requestedSeason, Math.round(amount * 1_000_000), lockedIds, excludedIds)
      if (seasonRef.current !== requestedSeason) return // the user moved to another season while this was solving
      setScenario(result)
      await reloadStatus(requestedSeason)
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
      await reloadStatus(season)
      const msg = `Imported ${result.accepted} salaries (${result.total} on file); ${result.issues.length} rows need review.`
      setMessage(msg); toast.success(msg)
    } catch (error) { const msg = error instanceof Error ? error.message : 'Salary import failed.'; setMessage(msg); toast.error(msg) }
    finally { setBusy(false) }
  }

  const coveragePct = status?.players ? Math.round((status.priced_players / status.players) * 100) : 0
  const liveLoaded = Boolean(status?.players) && !status?.is_demo

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
          <AccountPanel account={account} busy={busy} onChange={onAccountChange} />
          <ScenarioForm season={season} seasons={seasonChoices} cap={cap} lockedIds={lockedIds} excludedIds={excludedIds} busy={busy} onSeason={setSeason} onCap={setCap} onLockedIds={setLockedIds} onExcludedIds={setExcludedIds} onBuild={() => void build()} />
          <section className="data-panel card">
            <h2>Player data</h2>
            <p className="data-state">
              {status?.players ? <><strong>{status.priced_players}</strong> of <strong>{status.players}</strong> players have salaries</> : 'No player data loaded'}
            </p>
            {status?.players ? <><div className="coverage-bar" aria-hidden><div className="coverage-fill" style={{ width: `${coveragePct}%` }} /></div><CoverageDrawer season={season} coveragePct={coveragePct} priced={status.priced_players} total={status.players} /></> : null}
            {status?.snapshot_at && <p className="data-date">Updated {new Date(status.snapshot_at).toLocaleString()}</p>}
            {status?.is_demo && <p className="demo-tag">Fictional demo data</p>}
            <div className="data-actions">
              {status?.is_demo
                ? <button type="button" onClick={() => void action(async () => { await exitDemo(); setScenario(null) }, 'Demo data removed.')} disabled={busy}>Exit demo</button>
                : !liveLoaded && <button type="button" onClick={() => void action(async () => { await seedDemo(); setSeason(2026) }, 'Fictional demo data loaded.')} disabled={busy}>Try demo data</button>}
              <button type="button" onClick={() => void action(() => refreshMlb(season), 'Live MLB players refreshed. Import salaries to build a real-player roster.')} disabled={busy}>Refresh MLB players</button>
              {status?.players ? <a className="template-link" href={salaryTemplateUrl(season)} download>Download player template</a> : null}
              <label className="upload-button">Import salary CSV<input aria-label="Import salary CSV" type="file" accept=".csv,text/csv" disabled={busy || Boolean(status?.is_demo)} onChange={event => { const input = event.target; const file = input.files?.[0]; input.value = ''; void upload(file) }} /></label>
            </div>
            <p className="data-help">Real-player rosters need an attributed salary CSV. Imports add to the salaries already on file, and a player in the CSV replaces their earlier salary. Players without a salary are excluded and shown in the coverage report.{status?.is_demo ? ' Exit demo mode to import real salaries.' : ''}</p>
            {(savedScenarios.length > 0 || mineOnly) && (
              <div className="history">
                <div className="history-head">
                  <h3>Saved scenarios</h3>
                  {account && <label className="mine-toggle"><input type="checkbox" checked={mineOnly} onChange={e => setMineOnly(e.target.checked)} disabled={busy} />Only mine</label>}
                </div>
                {savedScenarios.length === 0 && <p className="data-help">You have no saved rosters for {season} yet.</p>}
                <ul className="history-list">
                  {savedScenarios.map(saved => {
                    const when = new Date(saved.created_at).toLocaleDateString()
                    return (
                      <li className="history-item" key={saved.id}>
                        <button type="button" className="history-button" disabled={busy} onClick={() => { setBusy(true); void getScenario(saved.id).then(s => { setScenario(s); toast.success('Scenario reopened') }).catch(() => { const m='Could not reopen that scenario.'; setMessage(m); toast.error(m) }).finally(() => setBusy(false)) }}>
                          <span>{saved.is_demo ? 'Demo' : 'Scenario'} · {when}{saved.owned_by_me ? ' · Yours, private' : ''}</span>
                          <strong>{saved.total_war.toFixed(1)} WAR</strong>
                          <small>{(saved.cap_usd / 1_000_000).toFixed(0)}m cap · {(saved.total_salary / 1_000_000).toFixed(1)}m payroll</small>
                        </button>
                        {saved.owned_by_me && <button type="button" className="history-delete" disabled={busy} aria-label={`Delete scenario from ${when}, ${saved.total_war.toFixed(1)} WAR`} onClick={() => void removeScenario(saved)}>Delete</button>}
                      </li>
                    )
                  })}
                </ul>
              </div>
            )}
          </section>
        </aside>
        <div className="results">
          {message && <div className="message" role="status">{message}</div>}
          <AlternativesAnnouncer scenario={scenario} busy={busy} />
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
                  {t==='roster'?'Roster':t==='depth'?'Depth chart':t==='contracts'?'Contracts (preview)':t==='market'?'Market (preview)':'Season lab (preview)'}
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
