# Change guide

[Русский](../ru/development/change-guide.md)

Use this map to locate all consumers of an existing field or behavior. It describes
maintenance of current interfaces, not a new interface design. Start with
[architecture](architecture.md) and [development/testing](development-and-testing.md).

## Change-impact matrix

| Change | Code and data to inspect together | Verification and documentation |
|---|---|---|
| Receiver parameter/default | `config.py`, `config_loader.py` allowlist/conversion, collector bounds and CLI overrides, runner-generated receiver config | Check configured and echoed values; update receiver guide, profiles and both language versions |
| Stand INI parameter | Relevant runner's `ConfigParser` loading/validation and command generation; `central_observability.py` for shared observability fields | Function-level checks with mocked commands; update mode/reference examples with editable hosts and output paths |
| Measurement interval, group size, timeout, retained count | Runner `[measurement]` mapping, receiver conversion/clamping, `START` JSON, firmware validation/echo and counters | Compare paired profiles; test integrity and applied parameters; update statistics/methodology, not just a default value |
| Firmware serial field or status | `arduino-meter.ino`, `measurement.cpp`, `serial_comm.py`, receiver dispatch/start/stop logic, database mapping, metrics consumers | Preserve newline JSON framing and session semantics; unit checks plus separately recorded hardware serial verification |
| Receiver stdout/start gate | Receiver readiness/progress print sites and supervised runner matching/callback/stdin handling | Run `test_run_stand_measurement.py`; update operational output examples in both languages |
| SQLite field/schema | `database.py` CREATE/ALTER and saves, summaries in both GPIO runners, trace import/summary, plotting queries and merger's explicit columns/schema | Use temporary old/new schema fixtures; check defaults, units, keys, replacement behavior and merge losses; update SQLite reference/statistics |
| Prometheus metric/label | `metrics_server.py`, query helper, trace importer, generated/static Prometheus config, dashboards; historical helpers only if actually used | Test emitted/query names and target selection without servers; live scrape/remote-write/dashboard checks remain separate |
| Cyclictest bundle/validation/publication | `run_linux_benchmark.py`, manifest schema/version/hashes, `publish_cyclictest.py` validation and sidecars, external `rt-results` importer | Test malformed/tampered/incomplete bundles and retry behavior; synchronize publication/methodology docs with importer compatibility |
| Profile/backend/tuning | `configs/stands/`, runner backend/start/cleanup code, external board mappings and binary/module paths | Keep paired experimental variables aligned; update target prerequisites and metadata; do not claim a new hardware result |
| Installed command/file | `.gear/rt-tester-tools.spec` install/wrapper/`%check` lists, runtime paths, source-only boundaries | Source tests first; package build/content checks only after explicit user approval |

## Serial and statistical semantics to preserve

`START {JSON}\n` is a firmware command; `started` is its applied-parameter echo.
The supervised readiness stdout line is a different, PC-side startup contract.
Keep session IDs consistent across command, group, status, DB and trace labels;
check stale statuses and zero-based group indexes. Interactive receiver commands
are not identical to the firmware command set.

Firmware sends exactly the configured number of requests per group, including
timeouts. A pending request is not resent; a missing response increments timeout
accounting and contributes no latency value. Whole-response-group mean and RMS
jitter are calculated before tail selection; `avg_latency_us` and `min_latency_us`
describe the retained worst tail, not the full population. Collector tail size is
derived from 5%, while firmware caps it to available responses. SQLite stores the
tail and jitter but not every serial summary field. Do not reinterpret historical
rows or fill missing metadata as if it had been measured. Definitions belong in
[measurement statistics](../reference/measurement-statistics.md).

## Profiles and data compatibility

For a controlled comparison, align interval, group count/size, response timeout,
board/backend and tuning unless that variable is the intended difference. Use
distinct output databases for sessions/profiles and truthful `target-*` metadata;
kernel labels alone do not establish the exact running kernel. Inspect runner
preflight and target-side board mappings when changing a board name.

Test profiles by parsing and generating commands, not executing the full runner.
`--dry-run` is not a filesystem-free validation API. Keep example hostnames,
paths and observability endpoints reader-editable. For collection without live
observability, account for the current receiver's synchronous Prometheus queries;
do not describe it as a network-free collector.

For DB work, account for global first-path selection, WAL transactions and
`INSERT OR REPLACE` group behavior. Historical migrations and merger columns are
explicit code, not automatic schema propagation. The merger omits
`trace_group_metrics` and is not a lossless backup; retain original artifacts.
Use temporary copies for mutation tests and immutable read-only access only for
static checkpointed evidence.

## Bilingual maintenance and completion

Update English and its Russian mirror in one change: commands, parameter names,
units, defaults, limits, artifact locations and verification claims must agree.
Translate explanations, not literal JSON keys, CLI flags, metrics or machine
stdout tokens. Explain GPIO, PREEMPT_RT and latency at first relevant use in the
Russian reading path. Language switches must resolve inside `docs/`:
English development → `../ru/development/<name>.md`; Russian development →
`../../development/<name>.md`.

Run the focused checks for the affected boundary, then the full unittest command
from [development/testing](development-and-testing.md). Review local links in both
languages. Record what actually ran, what was mocked, historical-data provenance
and pending stand/server checks in [validation](../reference/validation.md).
Documentation approval precedes the deferred RPM packaging stage; agreement on
the plan alone does not authorize a build.
