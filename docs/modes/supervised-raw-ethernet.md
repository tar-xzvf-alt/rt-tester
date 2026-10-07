# Supervised raw Ethernet

[Русский](../ru/modes/supervised-raw-ethernet.md)

This mode measures the complete Arduino/controller/raw-Ethernet/supervisor/runtime
round trip. `rt-tester-run-stand` owns the readiness barrier, workload, receiver,
and trace collection.

```text
Arduino → controller GPIO → raw Ethernet → supervisor → shared memory → runtime
Arduino ← controller GPIO ← raw Ethernet ← supervisor ← runtime response
```

For the handler baseline use [standalone GPIO](standalone-gpio.md); for scheduler
latency without GPIO use [Linux benchmarks](linux-benchmarks.md).

## Prepare a stand profile

The installed laboratory example is:

```text
/usr/share/rt-tester-tools/configs/stands/rockpi-plc-visionfive2-controller.conf
```

It assigns RockPI to runtime/supervisor and VisionFive 2 to the GPIO controller.
Copy and edit it for your network, board mappings, metadata, result paths, and
observability server. It uses installed `/usr/share/rt-supervisor`,
`/usr/share/rt-controller`, `/usr/bin/alt-rt-supervisor`, `/usr/bin/controller-emu`,
and `/usr/bin/runtime` from the separate `rt-supervisor-runtime-example` package.
A production PLC supplies its own runtime integration package.

After wiring, target installation, and profile adaptation:

```bash
rt-tester-run-stand --config ./supervised.conf \
  --groups 10 --no-prometheus --no-grafana
```

This checks collection without live observability; trace import relies on
Prometheus and is not established by this run. For a full observed run, use your
configured observability without those flags. `--verbose` prints commands and
foreground output. Normal output reports stand/session, preparation, group
completion, and anomalies; failures include command, status, and recent output.
All components still write the profile's log files.

## Pipeline and target changes

1. Run `[pc] network-check` when configured. Topology belongs to the profile/helper.
2. Synchronize both target clocks using `date -u -s`, unless `--skip-time-sync`.
   Trace metrics use explicit timestamps, so independently managed clocks still
   need to agree.
3. Run external `rt-supervisor/scripts/preflight_stand.sh` and
   `rt-controller/scripts/preflight_stand.sh` over SSH. These check configuration,
   interfaces, clocks, buffers, and controller GPIO/libgpiod; stressed runs also
   require `stress-ng` on the runtime board.
4. With `--build`, rebuild already deployed remote source trees. This runner has
   **no `--deploy`**. Configure `repo`, `build`, and `binary` for source workflows;
   installed profiles are not ready-made build profiles.
5. Start trace exporters on both targets (`:9201`), local Prometheus (normally
   `127.0.0.1:9091`), and configured Grafana/tunnel. Prometheus scrapes receiver,
   trace exporters, and runtime `node_exporter`. Legacy central profiles forward
   Grafana on `13000`; local managed profiles normally use `3001`.
6. Start configured stress, supervisor/runtime, and controller. Supervisor creates
   `/dev/shm/shmem_input` and `/dev/shm/shmem_output` and starts the runtime wrapper
   using `-r`.
7. Reset/STOP Arduino before controller startup. After the readiness barrier,
   resume the paused controller with `SIGUSR1`, then let receiver issue START.
   This keeps setup transitions out of the measurement trace sequence.
8. Run receiver with `--start --exit-on-stop`. Arduino times the GPIO round trip;
   controller sends BETH requests with trace metadata, supervisor exchanges payload
   with runtime through shared memory/futex, and controller toggles the response.
9. On auto-stop, stop target measurement/stress processes, import trace aggregates
   from Prometheus into SQLite, check alignment/anomalies, and print the dashboard
   URL with `session_id`.

Cleanup waits up to three seconds for PID-file supervisor/controller processes
before removing shared-memory names or starting replacements. Prometheus,
Grafana, and trace exporters can remain running for inspection:

```bash
rt-tester-run-stand --config ./supervised.conf --stop-observability
```

`--dry-run` is a command preview with possible generated-file writes and local
probes, not read-only validation. Use `--help` to inspect options.

## Network health and transport

Before and after collection the runner records `/proc/net/dev`,
`/proc/net/softnet_stat`, and, when available, `ethtool -S <iface>`. Drops, errors,
CRC, overflow, and underflow deltas are measurement anomalies. Host-wide per-CPU
`softnet.time_squeeze` is reported as a warning, not by itself a packet-loss
verdict. Controller logs timestamped `trace out-of-window edge` warnings for
edges beyond the configured measurement window.

The standard payload is a full **96 KiB** supervisor slot. Specialized experiments
may set `[transport] payload-size` (`RT_TRANSPORT_PAYLOAD_SIZE`). Other controls:

| Profile field | Target environment | Meaning |
|---|---|---|
| `response-timeout-ms` | `RT_RESPONSE_TIMEOUT_MS` | Controller response deadline before whole-cycle retry |
| `retransmit-timeout-ms` | `RT_RETRANSMIT_TIMEOUT_MS` | NACK retransmission interval |
| `gap-nack-retries` | `RT_GAP_NACK_RETRIES` | NACK attempts before abandoning an incomplete transport session |

Preflight raises `net.core.rmem_max` and `net.core.wmem_max` to at least 4 MiB
for the full payload. `requested retransmit` indicates frame recovery;
`retry_*` stages indicate retry of the complete request/response cycle.

## Inspect the result

The `RT Trace Stage Breakdown` dashboard UID is `rt-trace-stages`. It shows
runtime CPU/memory, RX/TX bytes/sec, Arduino round-trip latency, ordinary stages,
and retry stages. Latest stage metrics are `rt_trace_stage_latest_us` and
`rt_trace_stage_latest_count`; `rt_trace_stage_us` and `rt_trace_stage_count`
retain group-level values for SQLite import. Stepped lines show the latest
completed group, not a continuously sampled latency distribution.

Use several groups (typically ten) for dashboard checks so Prometheus has time
to scrape receiver metrics. Runtime load comes from `runtime_node_exporter`,
normally `<supervisor-host>:9100`; override with
`[observability] runtime-node-exporter-target` if needed. Network throughput uses
`rate(node_network_*_bytes_total)`, not a normalization by link speed.

The runner exits `2` with `Measurement completed with anomalies` for non-lifecycle
events, target log errors/warnings/timeouts, trace/group mismatch, contradictory
latencies, or network drop/error growth. Artifacts remain available for diagnosis.
`Arduino latency contradicts imported trace metrics` means a required trace stage
exceeds Arduino's maximum: investigate wiring, direct D7/D20 loopback/crosstalk,
and ground. `trace group count does not match receiver groups` can indicate extra
edges or trace activity outside the Arduino window. Explain these before comparing.

See [dependencies](../reference/dependencies.md), [receiver](../usage/receiver.md),
[central observability](../observability/central.md),
[analysis](../usage/analysis-and-reports.md), and
[GPIO methodology](../methodology/gpio-measurements.md).
