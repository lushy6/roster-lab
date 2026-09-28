import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { Scenario } from '../api'
import RosterView from './RosterView'

const scenario: Scenario = {
  id: 'scenario-1',
  season: 2026,
  cap_usd: 250_000_000,
  roster: { status: 'optimal', picks: [], total_salary: 0, total_war: 0 },
  alternatives: [],
  alternatives_truncated: true,
  is_demo: false,
  model_version: 'war-proxy-v3',
  snapshot_at: '2026-09-27T00:00:00Z',
  snapshot_id: 'snapshot-1',
  salary_id: 'salary-1',
}

describe('RosterView', () => {
  it('announces when some alternative rosters were omitted', () => {
    const markup = renderToStaticMarkup(createElement(RosterView, { scenario }))

    expect(markup).toContain('role="status"')
    expect(markup).toContain('Some alternative rosters were skipped to keep the build fast.')
  })
})
