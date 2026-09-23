import { describe, expect, it } from 'vitest'
import { rosterToCsv, toCsv } from './csv'
import type { Pick } from './api'

describe('toCsv', () => {
  it('joins plain cells with commas and CRLF line endings', () => {
    expect(toCsv([['a', 'b'], [1, 2]])).toBe('a,b\r\n1,2')
  })

  it('quotes cells containing commas, quotes or newlines, doubling embedded quotes', () => {
    expect(toCsv([['He said "hi"', 'a,b', 'line\nbreak']])).toBe('"He said ""hi""","a,b","line\nbreak"')
  })

  it('renders null and undefined as empty cells', () => {
    expect(toCsv([[null, undefined, 'x']])).toBe(',,x')
  })

  it('neutralises spreadsheet formulas in text but leaves real negative numbers alone', () => {
    expect(toCsv([['=SUM(A1)', '+1', '@cmd', '-2']])).toBe("'=SUM(A1),'+1,'@cmd,'-2")
    expect(toCsv([[-1.5]])).toBe('-1.5')
  })
})

const pick = (over: Partial<Pick>): Pick => ({
  player_id: 1, name: 'Ha-Seong Kim', team: 'Team, Inc', slot: 'SS', salary: 1_000_000, war: 2.345,
  uncertainty: 'low', input_seasons: [2024, 2025], hitting_war: 2, pitching_war: 0,
  salary_source_url: 'https://example.org/a?x=1,2', salary_checked_at: '2026-09-17', ...over,
})

describe('rosterToCsv', () => {
  it('keeps a comma-bearing source URL in a single column', () => {
    const rows = rosterToCsv([pick({})]).split('\r\n')
    expect(rows[0]).toBe('slot,player_id,name,team,salary_usd,war,slot_weight,counted_war,uncertainty,source_url')
    expect(rows[1]).toBe('SS,1,Ha-Seong Kim,"Team, Inc",1000000,2.35,1,2.35,low,"https://example.org/a?x=1,2"')
  })

  it('exports the slot weight and the WAR that actually counts toward the roster', () => {
    const rows = rosterToCsv([pick({ slot: 'BN1', war: 4, weight: 0.25 })]).split('\r\n')
    expect(rows[1]).toContain(',4.00,0.25,1.00,')
  })

  it('treats a saved scenario without weights as full weight', () => {
    expect(rosterToCsv([pick({ weight: undefined })]).split('\r\n')[1]).toContain(',2.35,1,2.35,')
  })
})
