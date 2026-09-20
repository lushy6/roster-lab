import { useState } from 'react'
import { motion } from 'framer-motion'
import type { Pick } from '../api'

const money = (v: number | null | undefined) => v == null ? 'N/A' : `$${(v/1_000_000).toFixed(1)}m`

function initials(name: string) {
  return name.split(' ').map(n=>n[0]).slice(0,2).join('').toUpperCase()
}

function StatLine({ pick }: { pick: Pick }) {
  const s = pick.stats || {}
  const hasHitting = s.ops || s.avg || s.hr
  const hasPitching = s.era && s.era !== 'null'
  // graceful: if genuinely missing, show — with zinc-500
  if (hasPitching && !hasHitting) {
    return (
      <span className="lg-stats tabular-nums">
        <span>{s.era ?? '—'} <span className="lg-label">ERA</span></span><span className="lg-dot" />
        <span>{s.ip ?? '—'} <span className="lg-label">IP</span></span><span className="lg-dot" />
        <span>{s.so ?? '—'} <span className="lg-label">SO</span></span>
      </span>
    )
  }
  const ops = s.ops && s.ops !== 'null' ? Number(s.ops).toFixed(3) : null
  const avg = s.avg && s.avg !== 'null' ? Number(s.avg).toFixed(3).replace(/^0/,'') : null
  const hr = s.hr ?? null
  const pa = s.pa ?? null
  if (!ops && !avg && !hr) return <span className="lg-stats lg-muted tabular-nums">— stats pending</span>
  return (
    <span className="lg-stats tabular-nums">
      {avg ? <><span>{avg}</span> <span className="lg-label">AVG</span></> : <span className="lg-muted">—</span>}<span className="lg-dot" />
      {ops ? <><span>{ops}</span> <span className="lg-label">OPS</span></> : <span className="lg-muted">— OPS</span>}<span className="lg-dot" />
      {hr !== null ? <><span>{hr}</span> <span className="lg-label">HR</span></> : <span className="lg-muted">— HR</span>}
      {pa !== null ? <><span className="lg-dot" />{pa} <span className="lg-label">PA</span></> : null}
    </span>
  )
}

function Headshot({ pick }: { pick: Pick }) {
  const primary = pick.headshot_url || ''
  const espnFallback = `https://a.espncdn.com/combiner/i?img=/i/headshots/mlb/players/full/${pick.player_id}.png&h=96&w=96&scale=crop`
  const [src, setSrc] = useState(primary)
  const [triedEspn, setTriedEspn] = useState(false)
  const [failed, setFailed] = useState(false)

  const handleError = () => {
    if (!triedEspn) {
      setTriedEspn(true)
      setSrc(espnFallback)
    } else {
      setFailed(true)
    }
  }

  return (
    <div className="lg-photo-wrap">
      {!failed && src ? (
        <img
          src={src}
          alt={pick.name}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={handleError}
        />
      ) : null}
      {failed && (
        <div className="lg-fallback" aria-hidden>
          <span>{initials(pick.name)}</span>
        </div>
      )}
      {/* team badge: FA with zinc-500 if free agent, else logo */}
      {pick.team_abbrev === 'FA' || !pick.team_logo_url ? (
        <span className="lg-team-fa">FA</span>
      ) : (
        <img
          className="lg-team"
          src={pick.team_logo_url}
          alt={pick.team}
          loading="lazy"
          onError={e => ((e.currentTarget as HTMLImageElement).style.display = 'none')}
        />
      )}
      <span className="lg-slot">{pick.slot}</span>
    </div>
  )
}

export default function LineupGraphic({ picks }: { picks: Pick[] }) {
  const starters = picks.filter(p => !p.slot.startsWith('SP') && !p.slot.startsWith('RP') && !p.slot.startsWith('BN') && p.slot !== 'C2')
  const bySlot = new Map(starters.map(p => [p.slot, p]))
  const order: [string, string][] = [
    ['C','Catcher'], ['DH','Designated Hitter'],
    ['1B','First Base'], ['2B','Second Base'], ['SS','Shortstop'], ['3B','Third Base'],
    ['LF','Left Field'], ['CF','Center Field'], ['RF','Right Field'],
  ]
  return (
    <div className="lineup-graphic">
      <div className="lg-header">
        <img className="lg-mlb" src="https://www.mlbstatic.com/team-logos/league-on-dark/1.svg" alt="MLB" loading="lazy" onError={e => ((e.currentTarget as HTMLImageElement).style.display='none')} />
        <div>
          <strong>Starting lineup</strong>
          <span>Reverse diamond · home at top</span>
        </div>
        <span className="lg-sub">Photos: MLB headshots · {starters.length} starters</span>
      </div>

      <div className="lg-field">
        <svg className="lg-svg" viewBox="0 0 640 420" aria-hidden preserveAspectRatio="xMidYMid meet">
          <defs>
            <radialGradient id="lgGrad" cx="50%" cy="28%" r="78%">
              <stop offset="0%" stopColor="rgba(255,255,255,0.07)" />
              <stop offset="55%" stopColor="rgba(255,255,255,0.015)" />
              <stop offset="100%" stopColor="rgba(0,0,0,0)" />
            </radialGradient>
          </defs>
          <rect x="0" y="0" width="640" height="420" fill="url(#lgGrad)" />
          <path d="M320 48 L452 148 L320 258 L188 148 Z" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="1.2" />
          <path d="M320 148 L452 148 L320 258 L188 148 Z" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="1" strokeDasharray="6 8" />
          <circle cx="320" cy="48" r="3.2" fill="rgba(255,255,255,0.9)" />
          <circle cx="452" cy="148" r="3.2" fill="rgba(255,255,255,0.9)" />
          <circle cx="320" cy="258" r="3.2" fill="rgba(255,255,255,0.9)" />
          <circle cx="188" cy="148" r="3.2" fill="rgba(255,255,255,0.9)" />
          <circle cx="320" cy="148" r="14" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
          <circle cx="320" cy="148" r="2.2" fill="rgba(255,255,255,0.12)" />
          <path d="M 88 118 Q 320 12 552 118" fill="none" stroke="rgba(255,255,255,0.045)" strokeWidth="1" />
        </svg>

        <div className="lg-grid" role="list">
          {order.map(([slot]) => {
            const pick = bySlot.get(slot)
            if (!pick) return <div key={slot} className="lg-empty" aria-hidden />
            const salaryLabel = pick.salary == null ? 'N/A' : money(pick.salary)
            const isUnpriced = pick.salary == null
            return (
              <motion.div
                key={slot}
                role="listitem"
                data-testid="roster-player"
                className="lg-card"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.32, ease: [0.23, 1, 0.32, 1] }}
                whileHover={{ scale: 1.02, filter: 'brightness(1.08)', borderColor: 'rgba(255,255,255,0.16)' }}
                whileTap={{ scale: 0.98 }}
              >
                <Headshot pick={pick} />
                <div className="lg-info">
                  <strong className="lg-name">{pick.name}</strong>
                  <span className="lg-teamline">
                    <span className={pick.team_abbrev === 'FA' ? 'lg-fa' : ''}>{pick.team_abbrev || pick.team}</span>
                    <span className="lg-dot" />
                    <span className={isUnpriced ? 'lg-na' : ''}>{salaryLabel}</span>
                    <span className="lg-dot" />
                    <span className="tabular-nums">{pick.war.toFixed(1)} WAR</span>
                  </span>
                  <StatLine pick={pick} />
                </div>
              </motion.div>
            )
          })}
        </div>
      </div>
      <div className="lg-legend">
        <span className="lg-legend-dot" /> Premium minimal field · <span className="tabular-nums">.256</span> <span className="lg-legend-muted">0.825 OPS · 31 HR</span> — missing <span className="tabular-nums">—</span> gracefully muted
      </div>
    </div>
  )
}
