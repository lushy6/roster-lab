# MLB Front Office Simulator — Project Backbone

**Date:** September 17, 2026  
**Status:** Design approved; implementation plan pending review

## Product goal

Build a browser-based front office simulator that helps a user assemble and compare MLB rosters under a chosen payroll limit. The first playable feature builds the highest-value hypothetical 26-player roster from players across MLB. Later features add multi-year contracts, acquisitions, and season outcomes without replacing the roster engine.

The payroll limit is a user-created scenario rule. It is not presented as an MLB hard salary cap. The first version uses reported base salary for the selected season, excluding bonuses and tax adjustments, rather than Competitive Balance Tax accounting.

## First playable scenario

The user chooses a season and a payroll cap, then runs the optimizer. The app shows:

- A valid 26-player roster organized by lineup, bench, rotation, and bullpen.
- Total salary, cap remaining, total estimated player value, and value per dollar.
- Each player's role, salary, estimated value, and the data dates and sources behind those numbers.
- At least two alternative valid rosters, including a lower-cost option and a higher-value option when the cap allows one.
- A clear explanation when the cap or available data cannot produce a valid roster.

The user can save a scenario, change the cap, lock or exclude players, and compare results. The first release treats every MLB player in the dataset as hypothetically available; team control and transaction feasibility arrive later.

## Roster rules

The default template has 26 distinct players: 13 position players and 13 pitchers. It fills one each of catcher, first base, second base, third base, shortstop, left field, center field, right field, and designated hitter; four bench slots; five starting pitchers; and eight bullpen slots. At least one bench player must be eligible at catcher. A player may fill only one roster slot. Multi-position eligibility may satisfy any one eligible slot.

The default template follows the ordinary 13-pitcher active-roster limit. A two-way player has one salary and one roster place, may contribute both hitting and pitching value when data supports it, and does not count against the pitcher-designation limit when the player meets MLB's two-way criteria. The first implementation should explicitly test this case. These roster-slot counts are a playable scenario template, not a claim that MLB mandates a particular rotation or bench composition. The rules engine keeps the template configurable for future scenarios and any rule changes.

## Player value model

The first value score is **estimated selected-season wins above replacement**, a transparent projection built from performance before the selected season, playing-time estimates, and regression toward league average. It must be labeled as the app's estimate, with its formula and input seasons visible. Historical WAR is an input or comparison point, never silently presented as a forward projection. Pitching and hitting contributions are calculated separately and combined only for qualified two-way players. Missing or thin player histories receive conservative estimates and a visible uncertainty flag.

The optimizer maximizes total estimated value subject to the roster, salary, lock, and exclusion constraints. It solves a binary integer optimization problem rather than ranking players by value per dollar. A returned roster must be checked against every constraint before display. Alternatives are separate valid solutions with different caps or objective settings; the UI must never imply an alternative is better under the same exact objective and constraints if it is not.

## Data and provenance

Live player identity, team, role, and performance data come from MLB's Stats API through a server-side adapter. The app records the fetch time, endpoint, season, and normalization version for each immutable data snapshot. Failed refreshes leave the most recent successful snapshot available and visibly marked with its age.

Single-season salary records come from a **curated public-source register**. Each record stores player ID, season, dollar amount, salary definition, source URL, date checked, and reviewer note. The first release supports a maintained CSV import into this register; it does not automatically scrape Baseball-Reference, Spotrac, or other sites whose terms restrict such use. The salary register is refreshed by an operator from publicly reported figures with attribution. If a salary is missing or ambiguous, the player is excluded from optimization and shown in a data-quality report; the app does not invent a salary. A later licensed salary feed can replace the import through the same adapter.

The player pool for a run is tied to one performance snapshot and one salary-register version. Saved scenarios retain those version IDs so a roster can be reproduced even after the live data changes. The source screen reports player coverage and exclusions before optimization.

## System boundaries

| Component | Responsibility | Interface |
| --- | --- | --- |
| Web app | Scenario controls, roster display, comparisons, provenance | JSON API |
| MLB adapter | Fetch and normalize player and performance data | Versioned player snapshot |
| Salary register | Import, validate, attribute, and version salary figures | Versioned salary records |
| Value model | Produce player-season value and uncertainty | Value table and model version |
| Roster optimizer | Solve and validate constrained roster selection | Scenario in, roster or infeasibility reason out |
| Scenario store | Save inputs, results, and data/model versions | Scenario ID and comparison history |

Use React and TypeScript for the browser app, Python and FastAPI for the API and optimizer, SQLite for the first local database, and a maintained integer-programming library for the solver. Keep the optimization and data adapters callable without the web UI so they can be tested independently. No account system is required in the first local release.

## Main user flow

1. Refresh MLB data and import a version of the salary register.
2. Review source dates and missing-salary coverage.
3. Choose season, cap, and optional player locks or exclusions.
4. Generate a roster and inspect its roles, total cost, projected value, and source details.
5. Save the scenario and compare it with another cap or player constraint.

The API validates cap input, season availability, incompatible locks/exclusions, and salary coverage before solving. It returns a specific infeasibility reason when possible, such as insufficient catcher depth or a cap below the cheapest valid roster.

## Roadmap

1. **Roster lab:** Live MLB data, attributed salary register, transparent value model, exact optimizer, saved and compared scenarios.
2. **Contract desk:** Multi-year salary schedules, options, arbitration estimates, and future payroll commitments.
3. **Acquisition desk:** Team ownership, free-agent and trade availability, trade packages, and transaction constraints.
4. **Season lab:** Playing-time allocation, injury and performance uncertainty, repeated season simulation, and playoff-odds estimates.

Each phase extends the same player IDs, dated snapshots, scenario record, and rules engine. Contract, acquisition, and season simulation outputs must distinguish observed facts, assumptions, and model estimates.

## Acceptance criteria for the first build

- A fresh data refresh or a cached snapshot produces a usable player pool with displayed source dates.
- Every optimized roster has 26 unique players, required role coverage, the configured pitcher count, and salary at or below the cap.
- Locking or excluding a player changes the result or produces an explicit infeasibility response.
- A two-way player is counted once for roster size and salary, with correct role accounting.
- A deliberately impossible cap returns an explanation and no invalid roster.
- A saved scenario can be reopened and yields the same result from its recorded data and model versions.
- The value-model explanation and salary attribution are accessible from each result.

## Known constraints

Public salary reporting can disagree on deferred compensation, bonuses, and cash-versus-tax accounting. The first build uses reported base salary for the selected season throughout each scenario and preserves the exact reported source for each number. Salary coverage limits the available player pool; the UI reports this rather than hiding it. MLB data access and usage terms must be checked before public deployment or broad redistribution. The local prototype uses cached, rate-limited requests and avoids third-party bulk scraping.

## Sources informing the design

- [MLB 26-man roster rules](https://www.mlb.com/glossary/transactions/26-man-roster)
- [MLB two-way player rules](https://www.mlb.com/glossary/rules/two-way-players)
- [MLB WAR glossary](https://www.mlb.com/glossary/advanced-stats/wins-above-replacement)
- [MLB Competitive Balance Tax glossary](https://www.mlb.com/glossary/transactions/competitive-balance-tax)
- [Sports Reference data-use policy](https://minors.baseball-reference.com/data_use.html)
