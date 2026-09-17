# Roster Lab

A local MLB front-office simulator. The first playable slice builds a hypothetical 26-player roster under a user-set payroll limit. It keeps player performance and attributed salary inputs separate.

## Development

From `backend`, run `..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`. From `frontend`, run `npm install` and `npm run dev`. The frontend expects the API on `http://localhost:8000`.

Salary CSV columns: `player_id,season,base_salary_usd,source_url,checked_at,reviewer_note`. `base_salary_usd` stores the annual player salary or payroll figure reported by the cited source. Missing salary excludes a player from optimization. `reviewer_note` is optional and is carried into saved scenario provenance.

The checked-in `data/salary-template-2026.csv` contains the complete 2026 MLB player snapshot used when it was generated, with salary and attribution fields intentionally blank for review. The populated `data/salary-register-2026.csv` is the imported 2026 register used by the local database. It contains 904 unique player salaries matched to MLB Stats API IDs; the remaining live players stay blank until an attributed source row is available.

The 2026 register is sourced from [The Baseball Cube's 2026 payroll snapshot](https://www.thebaseballcube.com/content/payroll_year/2026/), which aggregates opening-day roster salary figures from all 30 clubs. The source is an opening-day payroll snapshot, not an MLB luxury-tax calculation; its treatment of prorated or guaranteed amounts follows the source's roster tables. The register was captured on 2026-09-17. The raw roster-page export is kept in `data/the-baseball-cube-2026-roster.csv` for auditability. It includes repeated traded-player rows; `scripts/import_salaries_2026.py` collapses those rows, joins names to the live MLB player list, and writes the app's salary schema.

To rebuild the register after replacing the raw source export, run `.venv\Scripts\python.exe scripts\import_salaries_2026.py` from the project root. To load a CSV into a running app, use the **Import salary CSV** control or `POST /api/salaries/import?season=2026`.

## Value estimate

Version `war-proxy-v1` is an **approximate WAR-like estimate**, not an official WAR statistic or a validated forecast. It uses only the two seasons before the selected season. The most recent season receives weight 0.65 and the older one 0.35. OPS regresses toward .720 over 200 plate appearances; ERA regresses toward 4.20 over 50 innings. Projected playing time is the weighted prior playing time, capped at 650 plate appearances or 200 innings. The hitting estimate converts the OPS difference into runs using `(OPS - .720) × PA / 4`, then adds 2 replacement wins per 600 PA and a position adjustment. The pitching estimate uses `(4.20 - ERA) × IP / 9` runs and 2 replacement wins per 180 IP. Ten runs equal one win. It omits defense, park effects, detailed baserunning, and injury forecasts; the app exposes those limits with each result. Two-way estimates add hitting and pitching value once each.
