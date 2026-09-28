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

## Review findings and hardening phase (added 2026-09-27)

A static review on 2026-09-27 ran no tests, servers or builds. Everything above is kept as the record of completed work. This section adds findings and the work they imply, to do before the "Next build phases" specs. Tasks are listed from most to least critical.

| ID | Severity | Type | Location | Finding |
|---|---|---|---|---|
| RL-1 | Low | Confirmed | `backend/app/value.py:60`, `:64` | `inningsPitched` from the MLB Stats API uses baseball thirds notation ("180.2" means 180⅔ IP), but `_number()` parses it as a decimal. Weighted IP, projected IP, the ERA regression weight and pitching WAR are all slightly understated (up to 0.67 IP per season row). The sibling `mlb_predictor/mlbbet/data/pitcher_logs.py` documents this exact trap and uses `outs` instead. |
| RL-2 | Medium | Risk (latency and reliability) | `backend/app/main.py:318-330`, `optimizer.py:176-189` | One `POST /api/scenarios` can run up to seven 15-second CP-SAT solves synchronously: the primary, a cheapest-roster fallback, and for each alternative cap an avoid-solve, a plain re-solve and possibly its own fallback. The worst case is about 105 s on a request thread, and an infeasible 90% cap always triggers the extra re-solve. |
| RL-3 | Medium | Risk (performance; needs a timing check) | `backend/app/storage.py:121-136` | `latest_snapshot` loads and `json.loads` the full league snapshot (all players × 2 seasons of hitting, pitching and fielding) on **every** `/api/status`, `/api/players` (typeahead) and `/api/coverage` request. `data/roster.db` is about 27 MB. |
| RL-4 | Low | Confirmed | `backend/app/mlb.py:98-107` | The two-way heuristic sums `gamesStarted` across all fielding positions, **including P**. A starting pitcher with at least 60 PA and 20 IP counts as two-way without playing the field. That is rare since the universal DH, but it is not the intended rule. |
| RL-5 | Low | Risk | `backend/app/main.py:124` | CORS allows any `localhost` origin with every method, and there is no request-size limit on `POST /api/salaries/import`. This is acceptable for a local-only app; revisit if it is ever hosted. |

### Task 7: Bounded scenario builds (RL-2)

- Skip the plain re-solve when the avoid-solve failed as `infeasible` because of the cap (it cannot succeed either). Run the alternatives only after the primary succeeds, with a shared time budget of about 20 s. Return the alternatives that finished, and flag `alternatives_truncated`.
- **Verify:** an API test with a solver stub counts solve calls (at most 4 on the infeasible-alternative path). A timing test with `SOLVER_SECONDS` patched low shows the endpoint respects the budget.

**Status 2026-09-27:** Complete. A shared 20-second deadline covers all roster solves; the API reports truncated alternatives and skips a below-minimum duplicate solve. Verified: 4 solves at most on the infeasible-alternative path, deadline regression, backend 75 passed, frontend lint/typecheck/unit/e2e green.

### Task 8: Snapshot read path (RL-3)

- Cache the parsed latest snapshot in process, keyed on `(snapshot id, season)`, or store the players in a table and query just the needed columns. Measure first: record p50 and p95 for `/api/players?q=...` against the current `roster.db`.
- **Verify:** after the change, typeahead p95 is under 100 ms on the same database. A refresh or import invalidates the cache (test).

**Status 2026-09-27:** Complete. Parsed snapshots use an eight-entry LRU keyed by resolved DB path, snapshot ID, and season; snapshot/salary writes invalidate it. Import/refresh invalidation regression passes. On the same 27.6 MB `data/roster.db`, warmed 50-request `/api/players?q=a` p50/p95 improved from 37.90/55.38 ms to 14.45/15.59 ms. Verified backend 76 passed; frontend lint/typecheck, Vitest 9, Playwright 7 passed.

### Task 9: Correct innings parsing (RL-1)

- Parse `inningsPitched` as `whole + tenths/3`, or read `outs` when present. Use one helper in both `value.py` and `_candidates`.
- **Verify:** a unit test that `"180.2"` gives 180.667 IP. `test_value.py` golden numbers are updated with a note, and `MODEL_VERSION` is bumped to `war-proxy-v3`. Saved v2 scenarios keep their stored numbers.

**Status 2026-09-27:** Complete. A shared innings parser converts baseball thirds (and reads `outs`) in value projection, candidate eligibility, and MLB ingestion. `MODEL_VERSION` is `war-proxy-v3`; the `180.2` IP golden is 180.667 and pitching WAR is 3.108. A stored v2 scenario retains its saved WAR. Verified backend 78 passed; frontend lint/typecheck, Vitest 9, Playwright 7 passed.

### Task 10: Two-way rule (RL-4)

- Exclude position `P` rows from `recent_fielding_starts`.
- **Verify:** a fixture pitcher with 70 PA, 150 IP and 30 starts at P is not two-way. The existing two-way fixture still is.

**Status 2026-09-27:** Complete. Starts at position P no longer qualify as fielding starts. The 70 PA/150 IP/30 pitcher-start fixture stays non-two-way, and the existing RF two-way fixture remains true. Verified backend 79 passed; frontend lint/typecheck, Vitest 9, Playwright 7 passed.

### Review follow-up (2026-09-27)

**Status:** README now documents `war-proxy-v3`, baseball thirds notation and `outs`, and preservation of saved v2 scenario values. `Scenario.alternatives_truncated` is optional in the frontend type; the Compare budgets panel shows a skipped-alternatives note even if none remain. Screen-reader announcement comes from `AlternativesAnnouncer`, a `role="status"` region that App keeps mounted (the in-panel note mounted together with its text, which screen readers do not reliably announce); its text is empty while a build runs, so repeated truncated builds are announced again. Verified backend pytest (79 passed), frontend lint and typecheck, and Vitest (14 passed). E2E, remote CI and a real screen reader were not run for this follow-up.

### Sequencing

Tasks are ordered from most to least critical. Tasks 7 and 8 (the two Medium risks) are independent. Land them before the contract-accounting spec, since those scenarios will solve more often; measure Task 8's baseline first. Task 9 changes values and bumps the model version to `war-proxy-v3`, so ship it as its own release with updated golden numbers. Task 10 is small and can ride along with Task 9. RL-5 needs no work while the app stays local-only.

### Validation (follow-up unit checks run; e2e not run)

```powershell
cd backend; ..\.venv\Scripts\python.exe -m pytest
cd ..\frontend; npm run lint; npm run typecheck; npm run test:unit; npm run test:e2e
```
