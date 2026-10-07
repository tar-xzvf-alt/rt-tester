# VisionFive 2 Userspace vs Kernelspace, PREEMPT_RT

[Русский](../ru/results/visionfive2-userspace-vs-kernelspace-preempt-rt.md)

Historical report. Its original text does not state a calendar run date or full
handler/firmware revisions; recorded session IDs and kernel below provide the
known provenance. This is not output from the current reference walkthrough.

The non-RT baseline for the cross-kernel comparison is in
[VisionFive 2 Userspace vs Kernelspace, Non-RT](visionfive2-userspace-vs-kernelspace-non-rt.md).

## Methodology

The userspace and kernelspace handlers were measured on the same VisionFive 2,
with the same Arduino Mega firmware, wiring, CPU affinity, priorities, and
measurement parameters used by the non-RT v2 experiment:

- 100 groups;
- 1500 requests per group;
- 1000 us request interval;
- 10000 us response timeout;
- userspace handler on CPU 1 at FIFO 85;
- GPIO IRQ thread on CPU 1 at FIFO 99;
- `node_exporter` on CPUs 0 and 3 at `SCHED_OTHER`.

The RT sessions used kernel `6.18.18-rt-alt1.port.rv64` with
`CONFIG_PREEMPT_RT=y`. Stressed sessions used:

```text
stress-ng --cpu 4 --cpu-method int64 --vm 1 --vm-bytes 70% --vm-keep --timeout 0
```

Measurement started after a 60 second warm-up and six MemAvailable samples
over 25 seconds. The observed memory spread was between 0.06% and 0.19%.

## PREEMPT_RT idle sessions

| Mode | Session | Tail average, us | Group stddev, us | Avg jitter, us | Avg group max, us | Absolute max, us |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| userspace | 1785396919 | 186.24 | 2.67 | 49.79 | 234.80 | 308 |
| kernelspace | 1785397130 | 108.57 | 0.54 | 29.11 | 125.28 | 184 |

The idle result is affected by the `schedutil` governor and is included as an
RT userspace/kernelspace check, not as the primary cross-kernel comparison.

## PREEMPT_RT stressed sessions

| Pair | Mode | Session | Tail average, us | Group stddev, us | Avg jitter, us | Avg group max, us | Absolute max, us |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | userspace | 1785397362 | 86.69 | 2.20 | 9.14 | 129.08 | 164 |
| 1 | kernelspace | 1785397680 | 58.88 | 1.53 | 6.59 | 82.12 | 116 |
| 2 | kernelspace | 1785397985 | 58.83 | 1.78 | 6.52 | 83.08 | 112 |
| 2 | userspace | 1785398290 | 86.80 | 1.94 | 8.94 | 126.68 | 160 |
| 3 | userspace | 1785398601 | 87.06 | 2.20 | 9.02 | 127.60 | 160 |
| 3 | kernelspace | 1785398907 | 58.87 | 1.53 | 6.59 | 83.32 | 112 |

Across the three RT sessions, kernelspace tail average was 58.86 us versus
86.85 us for userspace, an improvement of 32.22%. Mean jitter was 6.57 us
versus 9.03 us, an improvement of 27.33%.

All eight full RT sessions completed with 150000 requests, 150000 responses,
and zero timeouts each. The six stressed sessions therefore validated 900000
requests without a lost response.

## Cross-kernel stressed comparison

| Mode | Non-RT tail average, us | RT tail average, us | Change | Non-RT avg jitter, us | RT avg jitter, us | Change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| userspace | 89.64 | 86.85 | -3.11% | 9.16 | 9.03 | -1.43% |
| kernelspace | 57.77 | 58.86 | +1.90% | 6.36 | 6.57 | +3.22% |

Negative change means lower latency on PREEMPT_RT. Under this sustained load,
PREEMPT_RT did not materially improve the absolute GPIO response latency. The
kernelspace threaded IRQ remained substantially faster than the userspace
handler on both kernels, but the non-RT and RT kernelspace results differed by
less than 2% in tail average.

## Artifacts

The original local paths identify provenance; they are not packaged artifacts:

```text
~/.local/state/rt-tester/visionfive2-handler-comparison-v2/comparison.db
~/.local/state/rt-tester/visionfive2-handler-comparison-rt/comparison.db
~/.local/state/rt-tester/visionfive2-handler-comparison-rt/idle-userspace-vs-kernelspace.png
~/.local/state/rt-tester/visionfive2-handler-comparison-rt/stressed-pair1.png
~/.local/state/rt-tester/visionfive2-handler-comparison-rt/stressed-pair2.png
~/.local/state/rt-tester/visionfive2-handler-comparison-rt/stressed-pair3.png
```

The tail-average values describe retained worst response samples. Avg jitter is
the average of whole-received-group standard deviations, not the tail standard
deviation. The original report does not fully define the separate group-stddev
aggregation; its labels and numerical values are retained without assigning a
new formula. The stated cross-kernel findings apply to these recorded conditions,
not to a guaranteed real-time bound or all PREEMPT_RT workloads. See
[statistics](../reference/measurement-statistics.md) and
[GPIO methodology](../methodology/gpio-measurements.md).
