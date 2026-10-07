# GPIO measurement methodology

[Русский](../ru/methodology/gpio-measurements.md)

Standalone and supervised modes share the Arduino timing model but measure
different target paths. Use one runner to own lifecycle; do not manually start
supervisor through CMake during a profile-driven experiment.

## Record and control conditions

1. Record board, kernel/configuration, target packages/revisions, firmware,
   electrical level adaptation, and physical wiring.
2. Keep group size, request interval, response deadline, group count, and retained
   tail size identical across compared runs. Normally `worst-count` is 5% of the
   requested group size, with a minimum of one.
3. Record CPU frequency/governor, cooling, CPU/IRQ affinity, FIFO priorities,
   housekeeping placement, and `node_exporter` scheduling.
4. Create workload through the runner; record warm-up, workload command, memory
   availability, and cleanup. Keep background services controlled.
5. Label userspace/kernelspace and RT/non-RT explicitly. Do not combine different
   conditions into an unlabeled series.
6. Preserve SQLite, profile, logs, raw supervised traces, and provenance.

For the first standalone userspace experiment use the
[walkthrough](../usage/standalone-gpio-walkthrough.md). The optional monitoring
profile is part of the conditions: scrape/exporter overhead can affect a run.
Even basic standalone runs check/pin target `node_exporter`.

## Mode-specific checks

Standalone supports installed userspace, configured userspace source deploy/build,
and kernelspace responder. Smoke each variant before comparison. For paired runs,
keep the idle/stress ordering and placement policy consistent.

Supervised runs must let `rt-tester-run-stand` control runtime, supervisor,
controller, Arduino readiness, stress, and trace collection. Import trace
aggregates and check session/group alignment before interpreting stage breakdown.

## Integrity before statistics

Check continuous group indexes, consistent session IDs, and for every current
group:

```text
requests_sent = responses_received + timeout_count
retained samples = available worst-tail samples
```

The tail may shrink when too few responses arrive; no-response groups have no
latency samples. Inspect timeouts separately: they are not included in latency
mean/jitter. Explain missing responses, sequence anomalies, network drops, and
fall/recovery events before comparing. Historical absent/defaulted counters and
unrecorded versions are unknown, not evidence of a clean run.

## Interpretation

Arduino `mean_latency_us` covers all received responses, `avg_latency_us` is the
worst-tail average, `min_latency_us` is the worst-tail minimum, and `jitter_us`
is whole-received-group population standard deviation. SQLite retains the tail
and jitter but not the whole-group mean. Plot tail averages, tail p95/p99,
maximum, group jitter summaries, and integrity counts; do not label tail
percentiles as whole-population percentiles. See
[measurement statistics](../reference/measurement-statistics.md).

The historical plotting thresholds are `--limit 75` for unloaded and
`--limit 250` for stressed data, in microseconds. `--top` controls selected tail
rows; neither option sets the Arduino deadline. Keep selection/threshold settings
consistent and disclose them. An observed maximum depends on run duration and
conditions and is not a guaranteed worst-case bound. Use repeated controlled
runs rather than a conclusion from one maximum.

See [analysis and reports](../usage/analysis-and-reports.md) and
[validation](../reference/validation.md).
