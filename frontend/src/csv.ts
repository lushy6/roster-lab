import type { Pick } from './api'

type Cell = string | number | null | undefined

// A text cell that starts with one of these is read as a formula by spreadsheet apps.
const FORMULA_START = /^[=+\-@\t\r]/
// A plain number such as "-0.50" cannot be a formula, so pre-formatted numeric text is left alone.
const PLAIN_NUMBER = /^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i

function cell(value: Cell): string {
  if (value == null) return ''
  let text = String(value)
  if (typeof value === 'string' && FORMULA_START.test(text) && !PLAIN_NUMBER.test(text)) text = `'${text}`
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/** RFC 4180 CSV: quotes cells with commas, quotes or newlines, and neutralises spreadsheet formulas in text. */
export const toCsv = (rows: Cell[][]): string => rows.map(row => row.map(cell).join(',')).join('\r\n')

export function rosterToCsv(picks: Pick[]): string {
  const header = ['slot', 'player_id', 'name', 'team', 'salary_usd', 'war', 'slot_weight', 'counted_war', 'uncertainty', 'source_url']
  const rows = picks.map(pick => {
    const weight = pick.weight ?? 1 // saved scenarios from before slot weights count in full
    return [pick.slot, pick.player_id, pick.name, pick.team, pick.salary, pick.war.toFixed(2), String(weight),
      (pick.war * weight).toFixed(2), pick.uncertainty, pick.salary_source_url]
  })
  return toCsv([header, ...rows])
}
