import type { Pick } from '../api'

const money = (v: number) => `$${(v/1_000_000).toFixed(1)}m`

// Reverse diamond: home at top, CF at bottom
const POS: Record<string, { left: string; top: string }> = {
  C:  { left: '50%', top: '10%' },
  '1B':{ left: '72%', top: '22%' },
  '2B':{ left: '62%', top: '38%' },
  SS: { left: '38%', top: '38%' },
  '3B':{ left: '28%', top: '22%' },
  LF: { left: '18%', top: '62%' },
  CF: { left: '50%', top: '78%' },
  RF: { left: '82%', top: '62%' },
  DH: { left: '50%', top: '22%' }, // offset near home
}

function StatLine({ pick }: { pick: Pick }) {
  const s = pick.stats || {}
  const isPitcher = pick.slot.startsWith('SP') || pick.slot.startsWith('RP') || !!s.era
  if (isPitcher && s.era) {
    return <span className="lg-stats">{s.era} ERA · {s.ip} IP · {s.so} SO</span>
  }
  // hitter line
  const ops = s.ops ? Number(s.ops).toFixed(3) : '—'
  const avg = s.avg ? Number(s.avg).toFixed(3).replace(/^0/,'') : '—'
  const hr = s.hr ?? '—'
  const pa = s.pa ?? '—'
  return <span className="lg-stats">{avg} · {ops} OPS · {hr} HR · {pa} PA</span>
}

function Card({ pick, slot }: { pick: Pick; slot: string }) {
  const pos = POS[slot] || { left: '50%', top: '50%' }
  return (
    <div className="lg-card" data-testid="roster-player" style={{ left: pos.left, top: pos.top }}>
      <div className="lg-photo-wrap">
        <img
          src={pick.headshot_url}
          alt={pick.name}
          loading="lazy"
          onError={e => { (e.currentTarget as HTMLImageElement).src = `https://ui-avatars.com/api/?name=${encodeURIComponent(pick.name)}&background=0f2a3f&color=fff&size=128` }}
        />
        {pick.team_logo_url && <img className="lg-team" src={pick.team_logo_url} alt={pick.team} onError={e => (e.currentTarget.style.display='none')} />}
        <span className="lg-slot">{slot}</span>
      </div>
      <div className="lg-info">
        <strong className="lg-name">{pick.name}</strong>
        <span className="lg-teamline">{pick.team_abbrev || pick.team} · {money(pick.salary)} · {pick.war.toFixed(1)} WAR</span>
        <StatLine pick={pick} />
      </div>
    </div>
  )
}

export default function LineupGraphic({ picks }: { picks: Pick[] }) {
  const starters = picks.filter(p => !p.slot.startsWith('SP') && !p.slot.startsWith('RP') && !p.slot.startsWith('BN') && p.slot !== 'C2')
  const bySlot = new Map(starters.map(p => [p.slot, p]))
  // ensure DH offset so it doesn't overlap C/1B/3B
  const dh = bySlot.get('DH')
  const showDH = dh ? <Card key="DH" pick={dh} slot="DH" /> : null

  return (
    <div className="lineup-graphic">
      <div className="lg-header">
        <img className="lg-mlb" src="https://www.mlbstatic.com/team-logos/league-on-dark/1.svg" alt="MLB" onError={e => (e.currentTarget.style.display='none')} />
        <span>Starting lineup — reverse diamond</span>
        <span className="lg-sub">Home at top · Photos from MLB headshots</span>
      </div>
      <div className="lg-field" aria-label="Baseball field">
        {/* field markings */}
        <div className="lg-diamond" aria-hidden />
        <div className="lg-bases"><span className="base b1" /><span className="base b2" /><span className="base b3" /><span className="base home" /></div>
        <div className="lg-mound" aria-hidden />
        {/* player cards */}
        {Array.from(bySlot.entries()).filter(([s]) => s !== 'DH').map(([slot, pick]) => (
          <Card key={slot} pick={pick} slot={slot} />
        ))}
        {/* DH sits near home, offset */}
        {showDH}
      </div>
      <div className="lg-legend"><span className="lg-dot" /> OPS/AVG/HR/PA for hitters · ERA/IP/SO for two-way/pitchers — from prior seasons used in war-proxy-v1</div>
    </div>
  )
}
