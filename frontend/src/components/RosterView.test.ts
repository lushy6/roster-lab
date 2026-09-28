import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { Scenario } from '../api'
import RosterView, { ALTERNATIVES_TRUNCATED_NOTICE, AlternativesAnnouncer } from './RosterView'

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

const announcer = (props: { scenario: Scenario | null; busy: boolean }) =>
  renderToStaticMarkup(createElement(AlternativesAnnouncer, props))
const emptyRegion = '<p class="sr-only" role="status" aria-live="polite"></p>'

describe('RosterView', () => {
  it('shows a note when some alternative rosters were omitted', () => {
    const markup = renderToStaticMarkup(createElement(RosterView, { scenario }))

    expect(markup).toContain(ALTERNATIVES_TRUNCATED_NOTICE)
  })
})

describe('AlternativesAnnouncer', () => {
  it('keeps an empty live region mounted before any scenario exists', () => {
    expect(announcer({ scenario: null, busy: false })).toBe(emptyRegion)
  })

  it('clears the region while a build runs so a repeated notice is announced again', () => {
    expect(announcer({ scenario, busy: true })).toBe(emptyRegion)
  })

  it('announces truncation once the build finishes', () => {
    const markup = announcer({ scenario, busy: false })

    expect(markup).toContain('role="status"')
    expect(markup).toContain(ALTERNATIVES_TRUNCATED_NOTICE)
  })

  it('stays empty when every alternative was built', () => {
    expect(announcer({ scenario: { ...scenario, alternatives_truncated: false }, busy: false })).toBe(emptyRegion)
    expect(announcer({ scenario: { ...scenario, alternatives_truncated: undefined }, busy: false })).toBe(emptyRegion)
  })
})
