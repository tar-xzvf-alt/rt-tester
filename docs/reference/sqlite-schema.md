# GPIO session SQLite schema

[Русский](../ru/reference/sqlite-schema.md)

`src/pc-receiver/database.py` creates the schema and applies compatibility changes.
Older databases may contain legacy columns/tables or missing metadata. Inspect
the actual database rather than inferring its version from its filename.

## `groups`

One row per Arduino group, unique on `session_id/group_index`:

```text
id, session_id, group_index
pc_timestamp, pc_timestamp_us, arduino_timestamp
jitter_us, delay_us, measurements_per_group, worst_count
requests_sent, responses_received, timeout_count
target_board, target_kernel, target_stress, target_payload
created_at
```

`pc_timestamp_us` is PC wall time captured when group handling begins, in Unix
microseconds. `pc_timestamp` is a separately sampled local wall-clock string at
database insertion, after metric queries/logging; it is not another representation
of the same instant and may be substantially later. `arduino_timestamp` comes
from firmware `millis()`, not Unix time.
`delay_us` stores the configured request interval. `jitter_us` is population
standard deviation over all received response latencies in that group. Firmware
whole-group `mean_latency_us` is **not stored** in this table.

For current data, check `requests_sent = responses_received + timeout_count`.
Legacy/defaulted zero counters do not prove that no requests were lost.

## `latencies`

```text
id, group_id, latency_us, rank_in_group
```

Only retained worst-tail samples are stored, ranked from largest downward.
`group_id` references `groups.id` with cascade delete. Tail size is limited by
available responses; a no-response group has no latency rows. Means/minima and
percentiles calculated from this table describe that tail, not the entire group.
Timeouts are not inserted as latency samples. See
[measurement statistics](measurement-statistics.md).

## `events`

```text
id, session_id, event_type
event_time, event_time_us, time_since_start_us
group_index, details, created_at
```

Records session lifecycle and missing-group fall/recovery events. Review events
beyond normal `start`/`stop` before interpreting a run.

## `soc_metrics`

```text
id, session_id, group_index, pc_timestamp
cpu_percent, memory_percent, cpu_max, mem_max
cpu_avg, mem_avg, samples_in_group, duration_ms, created_at
```

Per-group summaries queried from Prometheus. Their presence/sample count depends
on monitoring availability; absent data is not zero target load.

## `trace_group_metrics`

```text
id, session_id, group_index, host, stage
count, min_us, avg_us, max_us, created_at
```

Imported supervised stage aggregates, unique on session/group/host/stage. These
are aggregates, not raw per-request traces. The source-only merge utility does
not copy this table; preserve original supervised databases and raw traces.

## `schema_version`

```text
version, applied_at
```

Reserved but currently **unused** for automatic version tracking: code creates
the table but neither records nor checks a schema version. This is unrelated to
the versioned cyclictest bundle manifest.

SQLite is primary GPIO/supervised evidence. Dashboards and reports are derived
views. Use [receiver integrity checks](../usage/receiver.md) and
[analysis](../usage/analysis-and-reports.md), and keep provenance alongside it.
