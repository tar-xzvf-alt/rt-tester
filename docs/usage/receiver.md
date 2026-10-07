# PC receiver

[Русский](../ru/usage/receiver.md)

The receiver controls Arduino sessions, receives group JSON, queries optional
SoC metrics through Prometheus, and stores SQLite data. Mode runners normally
generate its config and own its lifecycle; do not start another receiver on the
same serial port. For your first collection use the
[standalone walkthrough](standalone-gpio-walkthrough.md).

The RPM includes receiver, trace importer, and trace summary. Plotting and merging
remain source-only tools. Code is in `src/pc-receiver/`; see
[dependencies](../reference/dependencies.md), [schema](../reference/sqlite-schema.md),
and [analysis](analysis-and-reports.md).

## Configuration

The local source `measurement.conf` is not portable without checking its `db`
and target metadata. Serial selection is separate. Important receiver parameters:

| Parameter | Meaning | Default |
|---|---|---|
| `db` | SQLite path | `./arduino_data.db` |
| `measurements-per-group` | Requests per group, 1–1500 | `1500` |
| `measurement-interval-us` | Minimum request interval | `300` |
| `response-timeout-us` | Deadline for one Arduino response | `10000` |
| `auto-stop-groups` | Group count; zero means unlimited | `2500` |
| `target-board`, `target-kernel` | Recorded metadata labels | `unknown` |
| `target-stress`, `target-payload` | Recorded `on`/`off` conditions | `off` |
| `prometheus-url` | Local query API | Stand-specific |

Automatic settings use nominal group duration
`measurements-per-group * measurement-interval-us`:

```text
worst-count = max(1, integer 5% of measurements-per-group)
timeout-us = nominal group duration * 3
check-interval-us = nominal group duration
```

Explicit `timeout-us` and `check-interval-us` override their calculated values.
They monitor missing groups on the PC; `response-timeout-us` independently
limits a single outstanding Arduino request. Actual group duration can exceed
the nominal duration when responses take longer than the interval.

Arduino `mean_latency_us` is the mean over **all received responses** in the
group; `avg_latency_us` is the mean of the **retained worst tail**, and
`min_latency_us` is that tail's minimum. `jitter_us` is whole-received-group
population standard deviation. Timeouts are counters, not latency samples.
SQLite does not store the whole-group mean field. See
[measurement statistics](../reference/measurement-statistics.md).

## Interactive and automated collection

```bash
rt-tester-receiver --params ./measurement.conf
```

Interactive commands are `start`, `stop`, and `exit`; every `start` creates a new
session. For a direct receiver run, use `--port /dev/ttyACM0` to select a port
explicitly and `--baud 115200` for baud rate; otherwise it uses discovery and the
default baud rate. These are receiver CLI options, not supported keys in the
measurement configuration. Automated collection:

```bash
rt-tester-receiver --params ./measurement.conf \
  --groups 3 --start --exit-on-stop
```

For external trace correlation, add an explicit `--session-id 123456`. The
receiver exposes metrics on port `9101`; Arduino gauges appear after a group
arrives, so an empty metrics response before collection is not proof of failure.

## Trace import

For a supervised session whose trace samples are retained in local Prometheus:

```bash
rt-tester-import-trace arduino_data.db 123456 \
  --prometheus-url http://localhost:9091
rt-tester-trace-summary arduino_data.db --session-id 123456
```

The importer fills `trace_group_metrics` by session/group/host/stage. The stand
runner normally performs this import itself. Keep its source SQLite database;
the merge tool does not copy trace aggregates.

## Integrity and state

For each group check `requests_sent = responses_received + timeout_count`,
continuous indexes, consistent session IDs, and the actual number of retained
latency samples. With too few responses the tail can be smaller than requested;
with no responses there are no latency samples. Missing historical counters are
unknown, not evidence of zero losses.

Receiver logs and `metrics_all_groups.log` use
`${XDG_STATE_HOME:-$HOME/.local/state}/rt-tester`. `RT_TESTER_STATE_DIR` overrides
this receiver state directory but does not move the SQLite database, remote logs,
or profile-specific observability files. See [runtime paths](../reference/runtime-paths.md).
