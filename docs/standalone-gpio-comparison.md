# Standalone GPIO Baseline Comparison

Дата прогона: 2026-07-10.

## Fresh Standalone GPIO Run

Команда:

```bash
rt-tester-run-gpio \
    --config /usr/share/rt-tester-tools/configs/stands/visionfive2-standalone-gpio.conf \
    --groups 100
```

Результат:

| Mode | Session | Groups | Latency rows | Min us | Avg us | Max us | SoC metrics | Events |
|------|---------|--------|--------------|--------|--------|--------|-------------|--------|
| `visionfive2-standalone-gpio` | `1783672537` | `100` | `500` | `356` | `439.008` | `532` | `100` | `start`, `stop` |

Prometheus/Grafana diagnostics:

| Check | Result |
|-------|--------|
| `arduino_latency_avg` samples over 30m | `1980` |
| `soc_cpu_percent` samples over 30m | `1980` |
| `runtime_node_exporter up` | `1` |
| Grafana | `http://127.0.0.1:3002/d/rt-standalone-gpio?var-session_id=1783672537` |

## Supervised Reference Sessions

Live supervised run was not possible during this pass: `visionfive2 end0` had no
carrier (`/sys/class/net/end0/carrier = 0`), so `bvcarm` at `10.43.0.2` was not
reachable. For comparison, the latest valid local supervised SQLite sessions were
used.

| Mode | DB | Session | Groups | Latency rows | Min us | Avg us | Max us | SoC metrics | Events |
|------|----|---------|--------|--------------|--------|--------|--------|-------------|--------|
| `bvcarm-supervised-visionfive2-controller` | `/tmp/rt-tester-bvcarm-visionfive2.db` | `1783426011` | `100` | `500` | `14764` | `17877.992` | `155056` | `100` | `start`, `stop` |
| `rockpi4-supervised-visionfive2-controller` | `/tmp/rt-tester-rockpi-visionfive2.db` | `1783256958` | `100` | `500` | `16224` | `18780.088` | `38796` | `100` | `start`, `stop` |

## Interpretation

The standalone GPIO baseline is around `0.44 ms` average latency for the selected
Arduino parameters. The supervised raw-Ethernet reference sessions are around
`17.9-18.8 ms` average latency for the same stored worst-latency row model.

The live supervised comparison should be repeated after restoring carrier on the
`visionfive2 end0 <-> runtime/controller peer` link.
