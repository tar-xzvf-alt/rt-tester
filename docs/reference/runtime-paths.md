# Runtime paths

[Русский](../ru/reference/runtime-paths.md)

| Mode | Primary artifact | PC state | Target/server state |
|---|---|---|---|
| Standalone GPIO | Configured SQLite database | Receiver logs, generated configs, monitoring state | Handler/stress logs |
| Supervised | SQLite including imported trace aggregates | Receiver and monitoring state | Runtime/controller logs and raw traces |
| Cyclictest | Finalized UUID bundle | Publication sidecars | Temporary staging, `rt-results` catalog |

## Reader-owned GPIO experiments

The neutral templates use `.rt-tester-example` placeholders. Convert these to
absolute paths using the [walkthrough preparation](../usage/standalone-gpio-walkthrough.md)
before running. Keep the edited profiles in a persistent experiment directory.

Relative paths do not share a single base: runner-managed paths generally use
its launch directory, while the receiver resolves a relative `[measurement] db`
from `src/pc-receiver/` in the source/installed tree. The runner's summary then
looks for that path from its own directory. A relative database can therefore
land in the wrong location or fail. Use an absolute profile `db` or an absolute
`--db` override, and absolute observability paths. Keep profiles, versions,
wiring notes, and logs with the database; use the same adapted profile for cleanup.

Older smoke profiles may use `/tmp`; laboratory comparison profiles may use
specific home/state directories. Copy and replace those paths before use.
Do not infer result location from the mode name.

Receiver logs and `metrics_all_groups.log` normally use:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/rt-tester
```

`RT_TESTER_STATE_DIR` overrides only this receiver state directory. It does not
move the SQLite database, target logs, Prometheus storage, Grafana files, or SSH
tunnel files set in the profile. Relative target paths resolve remotely; choose
them independently from PC paths.

SQLite is the primary artifact. Before copying a live WAL-mode database, use a
SQLite backup or stop writers and ensure a consistent copy; copying only `.db`
while WAL contains recent writes can omit data. Keep original supervised
databases: the merge tool does not copy `trace_group_metrics`.

## Cyclictest bundles and publication

Choose your own output root, for example:

```text
~/.local/state/rt-tester/cyclictest-results/<run_uid>/
~/.local/state/rt-tester/cyclictest-publish/<run_uid>.json
```

Collection first uses hidden `.<run_uid>.partial`; successful validation writes
a manifest and atomically renames to `<run_uid>`. Failed/incomplete directories
are not finalized evidence. Publication sidecars remain outside the finalized
bundle. Server staging is temporary; the default catalog location is
`/var/lib/rt-results-prototype/cyclictest.db`, configurable in `[publish] database`.

Live Prometheus remote write does not transfer GPIO SQLite or raw trace files.
Cyclictest bundle publication is a separate
[publisher workflow](../usage/publish-cyclictest.md). See
[analysis](../usage/analysis-and-reports.md) for derived reports and
[observability](../observability/central.md) for monitoring storage.
