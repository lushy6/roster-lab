// VITE_API_URL lets the e2e suite point the UI at its own isolated backend.
// The default uses the page's own host name, so the session cookie is same-site (localhost and 127.0.0.1 are different sites).
export const API: string = import.meta.env.VITE_API_URL ?? `http://${typeof window === 'undefined' ? '127.0.0.1' : window.location.hostname}:8000`

/** Every request carries the session cookie; the API only accepts it from local origins. */
const call = (url: string, init: RequestInit = {}) => fetch(url, { credentials: 'include', ...init })

type Stats = { ops?: string; avg?: string; hr?: string | number; rbi?: string | number; pa?: string | number; era?: string; ip?: string; so?: string | number; whip?: string }

export type Status = { season: number; snapshot_id: string | null; snapshot_at: string | null; salary_id: string | null; players: number; priced_players: number; is_demo: boolean; model_version: string }
export type Pick = { player_id: number; name: string; team: string; team_abbrev?: string; slot: string; salary: number; war: number; weight?: number; uncertainty: string; input_seasons: number[]; hitting_war: number; pitching_war: number; salary_source_url: string; salary_checked_at: string; salary_reviewer_note?: string; headshot_url?: string; team_logo_url?: string; stats?: Stats }
export type Roster = { status: string; picks: Pick[]; total_salary: number; total_war: number }
export type Scenario = { id: string; season: number; cap_usd: number; roster: Roster; alternatives: { cap_usd: number; roster: Roster; distinct_from_primary?: boolean }[]; alternatives_truncated?: boolean; is_demo: boolean; model_version: string; snapshot_at: string; snapshot_id: string; salary_id: string; mlb_source_urls?: string[]; salary_sources?: string[]; salary_coverage?: { priced_count: number; total_players: number; missing_player_ids: number[] } }
export type SavedScenario = { id: string; season: number; created_at: string; cap_usd: number; total_salary: number; total_war: number; is_demo: boolean; snapshot_id: string; salary_id: string; owned_by_me?: boolean }
export type Account = { id: string; email: string }
export type PlayerSearch = { id: number; name: string; team: string; team_abbrev?: string; primary_position: string; eligible_positions: string[]; is_priced: boolean; salary: number | null; war: number; uncertainty: string; headshot_url?: string; team_logo_url?: string; stats?: Stats }
export type MissingPlayer = { id: number; name: string; team: string; primary_position: string }
export type Coverage = { priced_count: number; total_players: number; missing_player_ids: number[]; missing_players: MissingPlayer[] }
export type ImportMode = 'merge' | 'replace'

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message)
    this.name = 'ApiError'
  }
}

/** Every call goes through here so an error response can never be mistaken for data. */
export async function parse<T>(response: Response): Promise<T> {
  let body: unknown = null
  try { body = await response.json() } catch { /* empty or non-JSON body */ }
  if (!response.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail
    const structured = typeof detail === 'object' && detail !== null ? detail as { message?: string; code?: string } : undefined
    const message = structured?.message || (typeof detail === 'string' ? detail : '') || `Request failed (${response.status})`
    throw new ApiError(message, response.status, structured?.code)
  }
  return body as T
}

export const salaryTemplateUrl = (season: number) => `${API}/api/salaries/template?season=${season}`

export const getStatus = (season: number) => call(`${API}/api/status?season=${season}`).then(parse<Status>)
export const getSeasons = () => call(`${API}/api/seasons`).then(parse<number[]>)
export const seedDemo = () => call(`${API}/api/demo/seed`, { method: 'POST' }).then(parse<{ players: number }>)
export const exitDemo = () => call(`${API}/api/demo`, { method: 'DELETE' }).then(parse<{ message: string }>)
export const refreshMlb = (season: number) => call(`${API}/api/refresh/mlb?season=${season}`, { method: 'POST' }).then(parse<{ players: number }>)
export const importSalaries = (season: number, csv: string, mode: ImportMode = 'merge') =>
  call(`${API}/api/salaries/import?season=${season}&mode=${mode}`, { method: 'POST', headers: { 'content-type': 'text/csv' }, body: csv })
    .then(parse<{ accepted: number; total: number; mode: ImportMode; issues: { code: string }[] }>)
// A build runs up to five solves of at most 15s each on the server; give up a little after that.
const BUILD_TIMEOUT_MS = 90_000
export const buildScenario = (season: number, capUsd: number, lockedIds: number[], excludedIds: number[]) =>
  call(`${API}/api/scenarios`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ season, cap_usd: capUsd, locked_ids: lockedIds, excluded_ids: excludedIds }),
    signal: AbortSignal.timeout(BUILD_TIMEOUT_MS),
  }).then(parse<Scenario>).catch(error => {
    if (error instanceof DOMException && error.name === 'TimeoutError') throw new ApiError('Building the roster took too long. Try again, or loosen the payroll limit.', 0, 'timeout')
    throw error
  })
export const listScenarios = (season: number, mine = false) => call(`${API}/api/scenarios?season=${season}${mine ? '&mine=true' : ''}`).then(parse<SavedScenario[]>)
export const getScenario = (id: string) => call(`${API}/api/scenarios/${id}`).then(parse<Scenario>)
export const getCoverage = (season: number) => call(`${API}/api/coverage?season=${season}`).then(parse<Coverage>)
export const searchPlayers = (season: number, q: string, limit = 12) =>
  call(`${API}/api/players?season=${season}&q=${encodeURIComponent(q)}&limit=${limit}`).then(parse<PlayerSearch[]>)

const json = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
export const getAccount = () => call(`${API}/api/auth/me`).then(parse<Account | null>)
export const register = (email: string, password: string) => call(`${API}/api/auth/register`, json({ email, password })).then(parse<Account>)
export const login = (email: string, password: string) => call(`${API}/api/auth/login`, json({ email, password })).then(parse<Account>)
export const logout = () => call(`${API}/api/auth/logout`, { method: 'POST' }).then(parse<{ message: string }>)
export async function deleteScenario(id: string): Promise<void> {
  const response = await call(`${API}/api/scenarios/${encodeURIComponent(id)}`, { method: 'DELETE' })
  if (response.status !== 204) await parse<never>(response)
}
