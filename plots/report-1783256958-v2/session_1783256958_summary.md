# Session 1783256958 — Report

**Board:** rockpi4-supervised-visionfive2-controller
**Kernel:** rockpi-6.12.90-rt-alt1
**Stress:** OFF
**Payload:** ON
**Interval:** 100000 µs
**Measurements/group:** 100
**Worst count/group:** 5

## Performance

| Metric | Value |
|---|---:|
| Groups | 100 |
| Average Jitter | 1869.4 µs |
| Falls | 0 |
| Min Latency (per-group avg) | 16596.0 µs |
| Max Latency (per-group avg) | 33181.6 µs |
| Overall Latency (global avg) | 18780.1 µs |
| Global Max Latency | 38796.0 µs |

## Threshold Exceedances

| Metric | Value |
|---|---:|
| Threshold | 75 µs |
| Total exceeds | 500 |
| Groups with exceeds | 100 |
| Maximum exceed | 38796 µs |

## SoC Metrics

| Metric | Value |
|---|---:|
| Average CPU | 12.6% |
| Max CPU | 22.0% |
| Average Memory | 2.9% |
| Max Memory | 2.9% |

## Data Integrity

- ✅ groups: 100 (0..99)
- ✅ latencies: 500
- ✅ trace: 1000 rows, 2 hosts, 10 stages
- ✅ events: {'start': 1, 'stop': 1}
- ✅ soc_metrics: 100 rows

## Trace Sources

- **rockpi**: 500 measurements
- **visionfive**: 500 measurements