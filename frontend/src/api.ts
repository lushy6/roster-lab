export const API = 'http://127.0.0.1:8000'

export type Status = { season: number; snapshot_id: string | null; snapshot_at: string | null; salary_id: string | null; players: number; priced_players: number; is_demo: boolean; model_version: string }
export type Pick = { player_id: number; name: string; team: string; slot: string; salary: number; war: number; uncertainty: string; input_seasons: number[]; hitting_war: number; pitching_war: number; salary_source_url: string; salary_checked_at: string; salary_reviewer_note?: string }
export type Roster = { status: string; picks: Pick[]; total_salary: number; total_war: number }
export type Scenario = { id: string; season: number; cap_usd: number; roster: Roster; alternatives: { cap_usd: number; roster: Roster; distinct_from_primary?: boolean }[]; is_demo: boolean; model_version: string; snapshot_at: string; snapshot_id: string; salary_id: string; mlb_source_urls?: string[]; salary_sources?: string[]; salary_coverage?: { priced_count: number; total_players: number; missing_player_ids: number[] } }
export type SavedScenario = { id: string; season: number; created_at: string; cap_usd: number; total_salary: number; total_war: number; is_demo: boolean; snapshot_id: string; salary_id: string }

async function parse<T>(response: Response): Promise<T> {
  const body = await response.json()
  if (!response.ok) throw new Error(body.detail?.message || body.detail || `Request failed (${response.status})`)
  return body as T
}

export type PlayerSearch = { id: number; name: string; team: string; primary_position: string; eligible_positions: string[]; is_priced: boolean; salary: number | null; war: number; uncertainty: string }

export const getStatus = (season: number) => fetch(`${API}/api/status?season=${season}`).then(parse<Status>)
export const seedDemo = () => fetch(`${API}/api/demo/seed`, { method: 'POST' }).then(parse<{ players: number }>)
export const refreshMlb = (season: number) => fetch(`${API}/api/refresh/mlb?season=${season}`, { method: 'POST' }).then(parse<{ players: number }>)
export const importSalaries = (season: number, csv: string) => fetch(`${API}/api/salaries/import?season=${season}`, { method: 'POST', headers: { 'content-type': 'text/csv' }, body: csv }).then(parse<{ accepted: number; issues: { code: string }[] }>)
export const buildScenario = (season: number, capUsd: number, lockedIds: number[], excludedIds: number[]) => fetch(`${API}/api/scenarios`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ season, cap_usd: capUsd, locked_ids: lockedIds, excluded_ids: excludedIds }) }).then(parse<Scenario>)
export const listScenarios = (season: number) => fetch(`${API}/api/scenarios?season=${season}`).then(parse<SavedScenario[]>)
export const getScenario = (id: string) => fetch(`${API}/api/scenarios/${id}`).then(parse<Scenario>)
export const searchPlayers = (season: number, q: string, limit = 12) => fetch(`${API}/api/players?season=${season}&q=${encodeURIComponent(q)}&limit=${limit}`).then(parse<PlayerSearch[]>)
