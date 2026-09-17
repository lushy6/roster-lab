export const API = 'http://127.0.0.1:8000'

export type Status = { season: number; snapshot_id: string | null; snapshot_at: string | null; salary_id: string | null; players: number; priced_players: number; is_demo: boolean; model_version: string }
export type Pick = { player_id: number; name: string; team: string; slot: string; salary: number; war: number; uncertainty: string; input_seasons: number[]; hitting_war: number; pitching_war: number; salary_source_url: string; salary_checked_at: string }
export type Roster = { status: string; picks: Pick[]; total_salary: number; total_war: number }
export type Scenario = { id: string; season: number; cap_usd: number; roster: Roster; alternatives: { cap_usd: number; roster: Roster }[]; is_demo: boolean; model_version: string; snapshot_at: string; snapshot_id: string; salary_id: string }

async function parse<T>(response: Response): Promise<T> {
  const body = await response.json()
  if (!response.ok) throw new Error(body.detail?.message || body.detail || `Request failed (${response.status})`)
  return body as T
}

export const getStatus = (season: number) => fetch(`${API}/api/status?season=${season}`).then(parse<Status>)
export const seedDemo = () => fetch(`${API}/api/demo/seed`, { method: 'POST' }).then(parse<{ players: number }>)
export const refreshMlb = (season: number) => fetch(`${API}/api/refresh/mlb?season=${season}`, { method: 'POST' }).then(parse<{ players: number }>)
export const importSalaries = (season: number, csv: string) => fetch(`${API}/api/salaries/import?season=${season}`, { method: 'POST', headers: { 'content-type': 'text/csv' }, body: csv }).then(parse<{ accepted: number; issues: { code: string }[] }>)
export const buildScenario = (season: number, capUsd: number, lockedIds: number[], excludedIds: number[]) => fetch(`${API}/api/scenarios`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ season, cap_usd: capUsd, locked_ids: lockedIds, excluded_ids: excludedIds }) }).then(parse<Scenario>)
