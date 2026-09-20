# MLB Roster Lab Implementation Plan

> **For agentic workers:** Implement the tasks in order. Keep one tested, reviewable change per task. Work inline unless the user asks for delegated agents.

**Goal:** Deliver the first playable slice of the approved front-office simulator: a browser app that builds and compares valid 26-player rosters under a user-set payroll limit.

**Architecture:** A React/TypeScript client calls a FastAPI service. The service maintains versioned MLB player/stat snapshots and an attributed salary register, derives a transparent projected-value estimate, solves roster selection as an integer program, and stores reproducible scenarios in SQLite.

**Tech stack:** Python 3.12+, FastAPI, Pydantic, SQLAlchemy, OR-Tools CP-SAT, pytest; React, TypeScript, Vite, Vitest, Playwright; SQLite.

**Spec:** [MLB Front Office Simulator — Project Backbone](mlb-front-office-simulator-spec.md)

## Global constraints

- Work in `outputs/roster-lab/` beneath the current workspace so the app is a user-facing deliverable. Initialize Git there when implementation starts; the current workspace is not a Git repository.
- Treat the cap as a hypothetical scenario rule. Use reported base salary for the selected season, in whole dollars.
- Keep live MLB data and salary records in separate adapters. Do not scrape Baseball-Reference or Spotrac.
- Preserve source URL, fetch/check time, season, and version for every input used in a saved result.
- If a player has no trusted salary, exclude the player and report the exclusion. Never use a silent zero or league-minimum fallback.
- Optimize a configured 26-player template with 13 position slots and 13 pitcher slots, including 2 catchers, 5 starters, and 8 relievers. Count a qualified two-way player once for size and salary.
- Every returned roster is independently validated before the API sends it.
- Use static fixtures in unit tests; reserve live network calls for a smoke test and user-triggered refresh.

## File map

| Path | Responsibility |
| --- | --- |
| `roster-lab/backend/app/domain.py` | Player, salary, projection, scenario, and roster types |
| `roster-lab/backend/app/mlb.py` | Rate-limited MLB Stats API adapter and normalization |
| `roster-lab/backend/app/salaries.py` | Attributed salary CSV import and coverage report |
| `roster-lab/backend/app/value.py` | Transparent selected-season value estimate |
| `roster-lab/backend/app/optimizer.py` | CP-SAT roster solver and independent validation |
| `roster-lab/backend/app/storage.py` | SQLite snapshots and scenarios |
| `roster-lab/backend/app/main.py` | FastAPI routes and error responses |
| `roster-lab/backend/tests/` | Domain, ingestion, model, solver, and API tests |
| `roster-lab/frontend/src/` | Scenario controls, roster view, comparison, source details |
| `roster-lab/frontend/tests/` | Browser-level scenario test |

---

### Task 1: Domain and attributed salary import

**Files:** Create `backend/pyproject.toml`, `backend/app/domain.py`, `backend/app/salaries.py`, `backend/tests/test_salaries.py`, `data/salary-register.example.csv`, and `README.md`.

**Interfaces:** `SalaryRecord(player_id: int, season: int, base_salary_usd: int, source_url: str, checked_at: date)`; `load_salary_csv(path: Path) -> tuple[list[SalaryRecord], list[ImportIssue]]`; `salary_coverage(player_ids: set[int], salaries: list[SalaryRecord]) -> Coverage`.

- [x] **Step 1: Initialize project and write a failing test.** Create `roster-lab/`, run `git init`, set up the Python package, then add:

```python
def test_salary_import_rejects_unattributed_and_duplicate_rows(tmp_path):
    path = tmp_path / "salaries.csv"
    path.write_text(
        "player_id,season,base_salary_usd,source_url,checked_at\n"
        "10,2026,1000000,https://example.org/10,2026-09-17\n"
        "10,2026,2000000,,2026-09-17\n"
        "10,2026,3000000,https://example.org/other,2026-09-17\n"
    )
    rows, issues = load_salary_csv(path)
    assert [(r.player_id, r.base_salary_usd) for r in rows] == [(10, 1000000)]
    assert {issue.code for issue in issues} == {"missing_source", "duplicate_player_season"}
```

- [x] **Step 2: Run `python -m pytest tests/test_salaries.py -q` and confirm the test fails because the importer does not exist.**
- [x] **Step 3: Implement strict CSV parsing.** Parse whole-dollar positive salary, HTTP(S) source URL, ISO date, and unique `(player_id, season)`. Return invalid rows as `ImportIssue`, never silently coerce them. Put only header and schema examples with clearly fictional IDs in `salary-register.example.csv`.
- [x] **Step 4: Run the test suite.** Add coverage cases for missing player salaries and season mismatch. Commit with `git commit -m "feat: add attributed salary register"`.

### Task 2: Live MLB snapshots and provenance

**Files:** Create `backend/app/mlb.py`, `backend/tests/test_mlb.py`; extend `domain.py`.

**Interfaces:** `fetch_player_snapshot(season: int, client: httpx.Client) -> PlayerSnapshot`; each normalized player has MLB ID, name, team, primary position, eligible positions, observed batting/pitching seasons, and source metadata.

- [x] **Step 1: Write a failing fixture-based normalization test.** Include a small JSON response with one catcher, one multi-position fielder, one pitcher, and one two-way player. Assert unique MLB IDs, correct role mapping, and the exact source endpoint and fetch time in the snapshot.
- [x] **Step 2: Run `python -m pytest tests/test_mlb.py -q` and confirm it fails.**
- [x] **Step 3: Implement the adapter.** Fetch `https://statsapi.mlb.com/api/v1/sports/1/players?season={season}` for the candidate pool, then fetch prior-season batting, pitching, and fielding stats in bounded batches. Derive position eligibility from prior-season fielding appearances plus primary position; do not make every player eligible at DH merely because they can bat. Use explicit request timeout, retry with backoff for transient failures, and a conservative request rate. Record URL, HTTP retrieval time, season, and adapter version.
- [x] **Step 4: Run unit tests, then one manual network smoke test for a selected season.** Check player count is nonzero and inspect a catcher, a starter, and a multi-position player. Commit with `git commit -m "feat: ingest versioned MLB player snapshots"`.

### Task 3: Transparent player value estimates

**Files:** Create `backend/app/value.py`, `backend/tests/test_value.py`; extend `domain.py`.

**Interfaces:** `project_values(snapshot: PlayerSnapshot, target_season: int) -> ValueSnapshot`, returning `estimated_war`, `hitting_war`, `pitching_war`, `uncertainty`, `inputs`, and `model_version` for every player.

- [x] **Step 1: Write failing tests for no future-data leakage, playing-time regression, and two-way addition.** For example:

```python
def test_projection_uses_only_seasons_before_target(player_factory, snapshot_factory):
    player = player_factory(history={2024: 2.0, 2025: 3.0, 2026: 20.0})
    result = project_values(snapshot_factory([player]), target_season=2026)
    assert 2026 not in result[player.id].input_seasons
    assert result[player.id].estimated_war < 20.0
```

- [x] **Step 2: Run `python -m pytest tests/test_value.py -q` and confirm failure.**
- [x] **Step 3: Implement version 1 as an explicitly approximate WAR model.** Calculate recent-season weighted offensive and pitching run estimates from MLB counting/rate stats, add documented positional and replacement adjustments, convert runs to wins using a stored runs-per-win constant, and regress rates and playing time toward league averages. Keep all constants in one versioned configuration object. For missing history, return a conservative estimate and `uncertainty="high"`. Ensure a qualified two-way player's hitting and pitching estimates add once each.
- [x] **Step 4: Run tests and inspect a printed explanation for three fixture players.** Document formula, constants, and known omissions in `README.md`. Commit with `git commit -m "feat: add transparent player value model"`.

### Task 4: Exact roster optimization and validation

**Files:** Create `backend/app/optimizer.py`, `backend/tests/test_optimizer.py`; extend `domain.py`.

**Interfaces:** `optimize_roster(players: list[Candidate], rules: RosterRules, cap_usd: int, locked_ids: set[int], excluded_ids: set[int]) -> RosterResult`; `validate_roster(result: RosterResult, rules: RosterRules, cap_usd: int) -> list[str]`.

- [x] **Step 1: Write failing tests with small player pools.** Cover a greedy-trap case where highest WAR-per-dollar loses to the exact optimum, an impossible cap, duplicate slot prevention, two-catcher coverage, pitcher limit, lock/exclude conflict, and a qualified two-way player counted once.
- [x] **Step 2: Run `python -m pytest tests/test_optimizer.py -q` and confirm failure.**
- [x] **Step 3: Implement the CP-SAT model.** Define binary `x[player, slot]` only for eligible pairs. Constrain each slot to one player, each player to at most one slot, total base salary to the cap, and lock/exclude IDs. Optimize integer-scaled estimated WAR; use salary and stable player ID only as deterministic tie breakers. Verify the solver status and call `validate_roster` before constructing a successful response. For infeasible cases, run a cheapest-valid-roster solve and position-coverage checks to report a useful reason.
- [x] **Step 4: Run optimizer tests.** Compare the returned objective with an exhaustive enumeration on tiny fixtures. Commit with `git commit -m "feat: solve and validate capped rosters"`.

### Task 5: Versioned storage and API

**Files:** Create `backend/app/storage.py`, `backend/app/main.py`, `backend/tests/test_api.py`; extend `backend/pyproject.toml`.

**Interfaces:** `POST /api/refresh/mlb`, `POST /api/salaries/import`, `GET /api/coverage`, `POST /api/scenarios`, `GET /api/scenarios/{id}`, `GET /api/scenarios/{id}/alternatives`. The scenario create request contains season, cap in whole dollars, locked IDs, and excluded IDs. The response contains roster, objective, provenance IDs, model version, and validation summary.

- [x] **Step 1: Write a failing API test against an in-memory SQLite database.** Create a scenario from fixtures, fetch it, and assert the same snapshot IDs, total salary, and player IDs. Add an impossible-cap request that returns a structured 422 response with an infeasibility code.
- [x] **Step 2: Run `python -m pytest tests/test_api.py -q` and confirm failure.**
- [x] **Step 3: Implement immutable snapshot tables and scenario storage.** Store source metadata, normalized player data, salary-register version, model version, request constraints, solver result, and creation time. Validate ID existence and conflicts before solving. Generate alternatives by resolving at specified nearby caps and label each alternative's cap; omit duplicates.
- [x] **Step 4: Run backend tests and an API smoke test with `uvicorn app.main:app --reload`.** Confirm that a failed live refresh leaves the latest successful snapshot usable and marks its age. Commit with `git commit -m "feat: persist and serve roster scenarios"`.

### Task 6: Playable web interface

**Files:** Create `frontend/package.json`, `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/components/ScenarioForm.tsx`, `frontend/src/components/RosterView.tsx`, `frontend/src/components/SourceDetails.tsx`, `frontend/tests/roster.spec.ts`, and frontend styling files.

**Interfaces:** The UI uses the API contract from Task 5. Cap input is displayed in dollars; source age, excluded-player count, model explanation, and infeasibility reason are visible.

- [x] **Step 1: Scaffold Vite React/TypeScript and write one browser test.** From a seeded test database, set a cap, run the optimizer, and assert 26 distinct players, total salary within the cap, and source dates visible. Change the cap and assert a second scenario can be compared.
- [x] **Step 2: Run `npx playwright test tests/roster.spec.ts` and confirm failure.**
- [x] **Step 3: Build the scenario form, roster view, alternatives panel, and source details.** Group roster slots into lineup, bench, rotation, and bullpen; show per-player salary and estimated WAR. Give cap input a sensible range and clear validation. Show loading, refresh failure, salary-coverage warning, and infeasible-roster states in plain language. Keep source and model labels adjacent to result totals.
- [x] **Step 4: Run the browser test and `npm run build`.** Inspect the main page at desktop and narrow viewport widths, fix clipped tables or controls, and commit with `git commit -m "feat: add roster lab interface"`.

## Final verification — 2026-09-20 ✅

- [x] `python -m pytest -q` — 28 passed
- [x] `npm run build` — 41 modules 27.38kB CSS / 284kB JS
- [x] `npx playwright test` — 1 passed builds and compares 26-player roster
- [x] Save scenario → restart → reopen — 82.858 WAR unchanged, snapshot 85f289f6-ea0b-4ec9-91ff preserved
- [x] Data-quality report — 904/1459 priced, missing IDs surfaced in CoverageDrawer

## Emil polish + extensions — 2026-09-20 ✅

- [x] 1. Player Search Autocomplete — `GET /api/players` + `PlayerPicker.tsx` debounced popover
- [x] 2. Coverage Drawer — `GET /api/coverage` missing_players + filter
- [x] 3. Payroll Gauge — threshold colors, 600ms width
- [x] 4. Roster Diff — `distinct_from_primary` new-count
- [x] 5. Uncertainty inspector — unc-dot + hitting/pitching title
- [x] 6. Export CSV — roster to `roster-2026-*.csv`
- [x] 7. Depth Chart — diamond `DepthChart.tsx`
- [x] 8. Contract Desk — 3yr flat `ContractDesk.tsx` (Roadmap Phase 2 stub)
- [x] 9. Acquisition Desk — `AcquisitionDesk.tsx` (Phase 3 stub)
- [x] 10. Season Lab — variance slider `SeasonLab.tsx` (Phase 4 stub)
- [x] Commit `d42df17` — 14 files, 899+

## Next build phases

After the roster lab is stable, write separate specs and plans for contract accounting, acquisition rules, and season simulation. Each phase should reuse player IDs, snapshots, scenario storage, and the rules engine defined here.
