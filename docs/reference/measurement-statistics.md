# Measurement statistics and terminology

[Русский](../ru/reference/measurement-statistics.md)

## What the GPIO experiment measures

**GPIO** means general-purpose input/output. The Arduino measures **latency**:
elapsed time from its request transition to the detected response transition.
Standalone latency includes GPIO, electrical adaptation, interrupt handling,
and the userspace handler. It is not a pure scheduler benchmark.

**PREEMPT_RT** is a Linux real-time preemption configuration. Record the actual
kernel and configuration; an RT label alone does not establish a latency bound.

A **session** is one START-to-stop measurement run. A **group** contains a fixed
number of attempted requests. The **retained worst tail** is the largest N
latencies from received responses in each group, normally 5% of group size.
Timeouts are counted separately and are not recorded as latency samples.

## Whole-group versus retained-tail statistics

For R received responses with latencies x, the whole-group mean is
`sum(x) / R`, and RMS jitter is `sqrt(sum((x - mean)^2) / R)`.

| Firmware JSON / live metric | Population and meaning | SQLite representation |
|---|---|---|
| `mean_latency_us` / `arduino_latency_mean` | Mean of **all received responses** in one group | No dedicated whole-group mean column |
| `avg_latency_us` / `arduino_latency_avg` | Mean of the **retained worst tail** | Recompute from that group's `latencies` rows |
| `min_latency_us` / `arduino_latency_min` | Smallest retained tail value, **not** whole-group minimum | Minimum of stored tail rows |
| `max_latency_us` / `arduino_latency_max` | Largest received response, included in the tail | Maximum of stored tail rows |
| `jitter_us` / `arduino_jitter` | Population standard deviation of **all received responses**, around their mean | `groups.jitter_us` |
| `worst_count` | Tail size reported by firmware | `groups.worst_count` |
| `requests_sent`, `responses_received`, `timeouts` | Attempted requests, responses, expired response deadlines | Corresponding counters, with `timeout_count` for `timeouts` |

Receiver JSON logs can retain the whole-group mean. The canonical SQLite schema
stores individual tail values and whole-group jitter, not every individual
response. Do not reconstruct whole-group mean or percentiles from the tail.
For equal tail counts per group, the pooled tail mean equals the average of
group tail means. With unequal counts, those statistics have different weights.

Firmware stores latencies as 16-bit values; elapsed values at or above 65535 µs
are saturated at 65535. Timing uses `micros()` on Mega; stored microseconds do
not imply 1 µs instrument resolution or calibrated absolute accuracy.

## Percentiles and limits

`p95` or `p99` of stored tail rows is a percentile **of the retained population**,
not a percentile of all requests. Reports must identify which population and
group selection they use. An observed maximum is not a proven worst-case bound.
Missing responses must be accounted for even if all retained values look small.

Plotter `--top` selects how many worst stored rows to analyze **per group**;
it cannot recover discarded responses. `--limit` is a plotting/analysis threshold
in microseconds, not a response deadline. Historical workflows use 75 µs for
unloaded and 250 µs for stressed plots; choose and document a meaningful threshold
for your experiment rather than treating these values as universal pass/fail limits.

Three independent timing settings must not be confused:

| Setting | Purpose |
|---|---|
| `measurement-interval-us` | Minimum interval before a new Arduino request; a pending response can extend it |
| `response-timeout-us` | Deadline for one pending Arduino response; firmware clamps it to 1–65535 µs |
| Receiver `timeout-us` | PC fall-monitoring timeout for missing group data; normally derived from nominal group duration |

The nominal group duration is `requests per group × interval`. Response waits,
serial transfer, and processing add time; the interval is not a guaranteed
sampling period. With missing responses, the group can take much longer.

## Integrity before interpretation

For current firmware, each completed group should satisfy
`requests_sent = responses_received + timeout_count`.
The reference no-loss run additionally requires all requested groups, contiguous
indexes from zero, zero timeouts, and the expected retained-row counts.
Legacy databases may lack counters: mark loss accounting unknown instead of
inventing a zero-loss result.

Separate GPIO round-trip results from cyclictest scheduler wake-up results.
Compare runs only when wiring, firmware, kernel, handler, affinity/priorities,
frequency policy, workload, interval, deadline, and retained population are known.
See the [walkthrough](../usage/standalone-gpio-walkthrough.md),
[GPIO methodology](../methodology/gpio-measurements.md), and
[schema](sqlite-schema.md).
