# Experiment-first bilingual documentation

Status: completed; finished documentation approved and RPM built and verified.

## Scope

Primary reader: experiment engineer. Secondary reader: developer.
English is canonical at existing paths; Russian mirrors reader documentation
under `docs/ru/` with language-switch links and equivalent operational content.
Keep modes, usage, methodology, reference, and results organization.

Create one complete standalone GPIO userspace experiment for VisionFive 2,
Arduino Mega 2560, and ALT Linux. Standard execution uses installed RPMs;
plotting uses an explicitly documented source checkout and dependencies.
Include hardware/software prerequisites, wiring and electrical level adaptation,
reader-owned configuration, smoke, collection, artifacts, integrity, a real
historical analysis example, diagrams, statistics definitions, and limits.

Provide three portable profile examples: collection without observability,
local Prometheus/Grafana, and central remote-write observability. Explain that
live metric delivery does not publish the primary SQLite database. Show how
to verify scraping, remote write, and dashboard data.

Add development/architecture.md, development/development-and-testing.md, and
development/change-guide.md in both languages. Correct statistical definitions,
merge limitations, and dry-run descriptions in existing reader documentation.
Keep historical results recognizable as dated evidence.

## Completion criteria

- English and Russian readers have equivalent engineer and developer paths.
- Commands and profile examples match existing CLI/config behavior.
- Examples use editable target/server values and reader-owned output paths.
- Historical examples identify provenance and unknown metadata; no new hardware
  results are invented.
- All reader Markdown documents have language switches, and local links/assets
  resolve in the packaged documentation tree.
- Relevant automated checks and real-data offline analysis pass.
- A validation record distinguishes executed checks from pending hardware and
  server walkthroughs.
- User receives a summary and documentation to review before packaging.

## Task graph

| Task | Depends on | Scope |
|---|---|---|
| 01 | — | Existing English docs and project/documentation entry points |
| 02 | — | Reference profiles, tutorial, statistics, visuals, validation |
| 03 | — | English/Russian developer documentation |
| 04 | 01, 02 | Russian mirror of engineer documentation |
| 05 | 01, 02, 03, 04 | Automated checks, offline analysis, review and fixes |
| 06 | 05 + user approval | New RPM; deferred until explicit approval |
