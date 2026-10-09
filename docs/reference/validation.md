# Documentation validation record

[Русский](../ru/reference/validation.md)

This record distinguishes checked documentation from hardware measurements.
The reference walkthrough is an executable procedure to validate on a prepared
stand, not a claim that a new reference run has already been performed.

## Preparation checks

| Check | Status | Evidence |
|---|---|---|
| Existing automated behavior tests | Passed before rewrite | 38 tests at baseline `5f05a38` |
| Updated automated suite | Passed | 43 tests, including bilingual examples and reference profiles |
| English/Russian local links and assets | Passed | Documentation unittest suite; external URLs and anchors are not validated |
| Example profile adaptation/generation | Passed | Isolated config tests; no runner lifecycle execution |
| Documented CLI syntax | Help inspected | Installed-wrapper paths are checked statically; source CLI help was exercised |
| Statistical definitions | Source checked | Firmware whole-group/tail algorithm and SQLite storage |
| Historical example statistics | Executed, read-only | Session `186819`: 2500 groups, 187500 tail rows, mean 164.679701 µs, max 348 µs |
| Historical source plotting | Executed | Documented analysis-copy snippet and latency command produced a PNG; original DB SHA256 unchanged |
| Historical SVG | Passed | All 25 plotted bins checked against source SQL aggregates |
| Reference integrity-check snippet | Executed on synthetic data | 100 no-loss groups and 7500 tail rows; this is not a hardware result |
| Hardware/firmware build and upload | Not executed | Requires Mega, AVR tooling, and stand |
| Reference RPM installation and GPIO run | Not executed | Requires target packages, wiring, and threaded IRQ |
| Local Prometheus/Grafana walkthrough | Not executed | Requires installed monitoring software and live collection |
| Central metric delivery | Not executed | Requires server/account and verified matching-session receipt |
| Release RPM build/install | Recorded separately | Finished documentation approved; see the build's artifact/log report for packaging results |

## Runner finalization checks — 2026-10-09

- Full automated suite: **69 tests passed**, including 19 runner-cleanup tests.
- GPIO/stand startup failures, independent final actions, preserved interrupts,
  broken warning output and retained cyclictest bundles were checked through
  runner entry points with mocked SSH and temporary files.
- Local shell simulations checked failed signals, retained PID files,
  process-group workers after leader exit, zombie handling and the cyclictest
  directory-retention guard. No real target processes were signalled.
- Real short local child processes checked supervised gate success, broken stdin,
  TERM-ignoring receiver cleanup and interruption during teardown.
- Source GPIO/stand/cyclictest CLI help and `git diff --check` passed.
- Remote SSH cleanup, actual supervisor/runtime process-group behavior, GPIO
  hardware and an RPM build/install were not executed for this change.

## Stand acceptance checklist

Record date, package/revisions, board revision, kernel configuration, firmware
tool/library versions, electrical mapping/levels, CPU/governor settings, and
actual profile with each executed check.

1. Install the PC RPM and required target packages; inspect command help.
2. Build/upload firmware and verify serial access at 115200.
3. Verify target header mapping, level adaptation, common GND, and independent
   request/response; confirm handler/IRQ affinity and scheduling.
4. Complete basic three-group smoke: 4500 requests/responses, zero timeouts,
   groups 0–2, 225 retained rows.
5. Complete 100-group collection: 150000 requests/responses, zero timeouts,
   groups 0–99, 7500 retained rows; inspect events and diagnostics.
6. Analyze the saved DB and verify the graph's statistic population.
7. Execute local observability: verify endpoints, both scrape jobs, matching
   session metrics, Grafana datasource/variables, and cleanup.
8. Execute central observability: verify SSH forwards, remote-write receiver,
   matching session with collector label at the destination, dashboard, and
   queue drain before cleanup.

A failed or unexecuted step remains visible in the record. A healthy tunnel or
dashboard screenshot alone does not verify measurement integrity or delivery of
all groups. When reviewing historical data, mark unavailable counters/versions
unknown instead of applying the current no-loss acceptance criteria retroactively.
