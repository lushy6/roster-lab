# Roster Lab

A local MLB front-office simulator. The first playable slice builds a hypothetical 26-player roster under a user-set payroll limit. It keeps player performance and attributed salary inputs separate.

## Development

From `backend`, run `..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`. From `frontend`, run `npm install` and `npm run dev`. The frontend expects the API on `http://localhost:8000`.

Salary CSV columns: `player_id,season,base_salary_usd,source_url,checked_at`. Salary means reported base salary for that season. The example CSV contains a fictional ID and is only a schema example. Missing salary excludes a player from optimization.

## Value estimate

Version `war-proxy-v1` is an **approximate WAR-like estimate**, not an official WAR statistic or a validated forecast. It uses only the two seasons before the selected season. The most recent season receives weight 0.65 and the older one 0.35. OPS regresses toward .720 over 200 plate appearances; ERA regresses toward 4.20 over 50 innings. Projected playing time is the weighted prior playing time, capped at 650 plate appearances or 200 innings. The hitting estimate converts the OPS difference into runs using `(OPS - .720) × PA / 4`, then adds 2 replacement wins per 600 PA and a position adjustment. The pitching estimate uses `(4.20 - ERA) × IP / 9` runs and 2 replacement wins per 180 IP. Ten runs equal one win. It omits defense, park effects, detailed baserunning, and injury forecasts; the app exposes those limits with each result. Two-way estimates add hitting and pitching value once each.
