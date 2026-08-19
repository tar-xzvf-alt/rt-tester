# VisionFive 2 userspace vs kernelspace GPIO comparison v2

## Methodology

Both implementations were measured with the same Arduino Mega firmware,
wiring, kernel, CPU affinity, priorities, and measurement parameters:

- 100 groups;
- 1500 requests per group;
- 1000 us request interval;
- 10000 us response timeout;
- userspace handler on CPU 1 at FIFO 85;
- GPIO IRQ thread on CPU 1 at FIFO 99;
- `node_exporter` on CPUs 0 and 3 at `SCHED_OTHER`.

The Arduino allows only one outstanding request. A response timeout is stored
as a lost response and never causes a retry with a new timestamp. Every valid
session must therefore have exactly 150000 requests, 150000 responses, and no
timeouts.

The stressed sessions used:

```text
stress-ng --cpu 4 --cpu-method int64 --vm 1 --vm-bytes 70% --vm-keep --timeout 0
```

Measurement started only after a 60 second warm-up and six MemAvailable
samples over 25 seconds. The observed memory spread was below 0.11%.

## Idle sessions

| Mode | Session | Tail average, us | Avg jitter, us | Avg group max, us | Absolute max, us |
| --- | ---: | ---: | ---: | ---: | ---: |
| userspace | 1785387676 | 304.83 | 83.91 | 364.68 | 696 |
| kernelspace | 1785387677 | 228.62 | 63.53 | 277.00 | 480 |

The idle result is affected by the `schedutil` governor. CPU load keeps the
target at a higher frequency in stressed sessions, so idle and stressed
absolute values must not be compared as if frequency were fixed.

## Stressed sessions

| Pair | Mode | Session | Tail average, us | Group stddev, us | Avg jitter, us | Avg group max, us | Absolute max, us |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | userspace | 1785388092 | 89.08 | 2.96 | 9.06 | 139.04 | 224 |
| 1 | kernelspace | 1785388093 | 57.38 | 1.74 | 6.32 | 98.92 | 320 |
| 2 | kernelspace | 1785388974 | 58.72 | 1.87 | 6.54 | 98.96 | 236 |
| 2 | userspace | 1785388975 | 90.43 | 2.56 | 9.33 | 147.20 | 248 |
| 3 | userspace | 1785388976 | 89.41 | 2.36 | 9.11 | 145.56 | 256 |
| 3 | kernelspace | 1785388977 | 57.20 | 1.52 | 6.22 | 86.64 | 128 |

Across three sessions, kernelspace tail average was 57.77 us versus 89.64 us
for userspace, an improvement of 35.6%. Mean jitter was 6.36 us versus 9.16
us, an improvement of 30.6%. All six sessions completed with 150000 requests,
150000 responses, and zero timeouts each.

## Artifacts

```text
~/.local/state/rt-tester/visionfive2-handler-comparison-v2/comparison.db
~/.local/state/rt-tester/visionfive2-handler-comparison-v2/idle-userspace-vs-kernelspace.png
~/.local/state/rt-tester/visionfive2-handler-comparison-v2/stressed-userspace-vs-kernelspace.png
~/.local/state/rt-tester/visionfive2-handler-comparison-v2/stressed-pair2.png
~/.local/state/rt-tester/visionfive2-handler-comparison-v2/stressed-pair3.png
```
