# Roster Lab

A local MLB front-office simulator. The first playable slice builds a hypothetical 26-player roster under a user-set payroll limit. It keeps player performance and attributed salary inputs separate.

## Development

From `backend`, run `..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`. From `frontend`, run `npm install` and `npm run dev`. The frontend expects the API on `http://localhost:8000`.

Salary CSV columns: `player_id,season,base_salary_usd,source_url,checked_at`. Salary means reported base salary for that season. The example CSV contains a fictional ID and is only a schema example. Missing salary excludes a player from optimization.
