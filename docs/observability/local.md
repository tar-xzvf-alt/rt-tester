# Local Prometheus and Grafana

[Русский](../ru/observability/local.md)

Use this after the [basic GPIO walkthrough](../usage/standalone-gpio-walkthrough.md)
works. Prometheus collects live time series; Grafana displays them. Neither
replaces the SQLite experiment artifact. No central server or SSH forwarding is
needed in this scenario.

```text
Arduino → receiver :9101 ──┐
                          ├→ PC Prometheus :9092 → PC Grafana :3002 → browser
target node_exporter :9100 ┘
receiver → primary SQLite database (independent of dashboard storage)
```

## 1. Prepare software and your local profile

Install available ALT packages on the PC:

```bash
apt-get install prometheus grafana
command -v prometheus grafana-server
```

The runner expects Grafana's home directory `/usr/share/grafana`. Adapt the
installation if your package uses a different layout. Ports 9101, 9092, and 3002
must be free; receiver currently fixes its port at 9101. A scrape `receiver-port`
setting alone cannot change the receiver's listening port.

Use the copied/adapted `visionfive2-gpio-local.conf` from the walkthrough. Keep
the same measurement/target settings as the basic experiment. Its key difference:

```ini
[observability]
remote-write-url =
prometheus-port = 9092
prometheus-url = http://127.0.0.1:9092
receiver-port = 9101
grafana-managed = true
grafana-port = 3002
grafana-url = http://127.0.0.1:3002/d/rt-standalone-gpio
```

Keep the complete profile's absolute PID/log/data/config paths and editable
`node-exporter-target`. A blank remote-write URL disables central transport.
`node_exporter` must be running on the target before collection.
The runner generates scrape configuration, datasource UID `rt-gpio-prometheus`,
and file dashboard provisioning from installed assets; you do not need to
manually import the standalone dashboard for a newly managed Grafana instance.

## 2. Run a dashboard smoke

Run from the saved experiment directory:

```bash
OBS_SESSION=$(date +%s)
rt-tester-run-gpio --config ./visionfive2-gpio-local.conf \
  --session-id "$OBS_SESSION" --groups 10 \
  --db "$PWD/.rt-tester-example/local-observability.db"
```

Use several groups: with the reference settings, a group takes about 1.5 seconds
nominally, while Arduino gauges are scraped every 500 ms. A one-group run may
finish before a scrape captures it. Copy the printed session ID and Grafana URL.

## 3. Check the path while the run is active

From another PC terminal:

```bash
curl -fsS http://127.0.0.1:9101/health
curl -fsS http://127.0.0.1:9101/metrics
curl -fsS http://127.0.0.1:9092/-/ready
curl -fsS http://127.0.0.1:3002/api/health
```

After the first completed group, receiver `/metrics` should include
`arduino_latency_mean`, `arduino_latency_avg`, and `arduino_jitter`, with
`session_id` matching the run. Before that, the response can be empty.
Receiver listens on all PC interfaces; local scrape uses loopback.

At `http://127.0.0.1:9092/targets`, both jobs should be UP during collection.
Use the Prometheus query page or stable HTTP API:

```bash
curl -fsSG http://127.0.0.1:9092/api/v1/query \
  --data-urlencode 'query=up{job="arduino_latency"}'
curl -fsSG http://127.0.0.1:9092/api/v1/query \
  --data-urlencode 'query=up{job="runtime_node_exporter"}'
```

Both should have value `1` while their endpoints run. Query
`arduino_latency_avg{session_id="YOUR_SESSION_ID"}` and confirm your session.
After receiver exits, its `up` becomes 0 and current gauges eventually disappear;
select the experiment time range or query
`max_over_time(arduino_latency_avg{session_id="YOUR_SESSION_ID"}[1h])`.
`monitor`, `collector`, and `stand` are external labels for remote delivery,
not local scraped labels, so do not filter local queries on those labels.

## 4. Check Grafana and preserve data

Open the printed URL:

```text
http://127.0.0.1:3002/d/rt-standalone-gpio?var-session_id=YOUR_SESSION_ID
```

Select board `visionfive2`, the actual session, and a time range covering the run.
The standalone dashboard shows tail latency, jitter, and target CPU/memory.
“Average” refers to the worst-tail mean; the exported whole-group mean is a
different metric. See [measurement statistics](../reference/measurement-statistics.md).

If Prometheus has data but Grafana is empty, check datasource UID
`rt-gpio-prometheus`, URL `http://127.0.0.1:9092`, dashboard variables/time range,
and Grafana logs. If the port already belongs to an unmanaged Grafana, the runner
reuses it and does not automatically provision its datasource/dashboard; configure
that instance explicitly or stop it before using the managed example.

Preserve SQLite, edited profile, logs, versions, and notes. CPU/memory enrichment
can be incomplete; verify its coverage before correlating it with latency.
Prometheus gauges describe the latest group and are not a lossless group archive.

## 5. Stop managed monitoring

The measurement handler is cleaned up automatically; monitoring remains available.
From the same experiment directory/profile:

```bash
rt-tester-run-gpio --config ./visionfive2-gpio-local.conf --stop-observability
```

This stops processes identified by the profile's PID files. It does not erase
SQLite or TSDB data or stop unrelated distribution services. For remote metric
delivery, continue with [central observability](central.md).

## Generic supervised dashboard

`grafana/dashboards/rt-supervised-overview.json` (UID `rt-supervised-overview`)
provides full-width GPIO latency and RMS jitter, individual trace stages, group
integrity, and load metrics for a selectable PLC runtime board. It has no fixed
board names, target addresses, or network interface. The existing file provider
includes it when the packaged dashboard directory is provisioned; an unmanaged
Grafana can import the JSON and configure its hidden Prometheus datasource. The older
`rt-trace-stages` dashboard and laboratory dashboard remain available.

Select variables in this order:

1. **PLC runtime board** — `board` discovered from supervisor `runtime_wait`
   trace series, not from the receiver's display metadata.
2. **Kernel** — saved kernel labels of that board's sessions, or `All`.
3. **Stress** — saved load scenario: normally `off` or `on`, or `All`.
4. **Session** — sessions matching board, kernel and stress, or `All`.
5. **Stage statistic** — `min`, `avg`, `max`, or `All`.

Kernel and stress options come from receiver `arduino_session_info`, associated
with supervisor sessions by `(stand, session_id)`. They reflect `target-kernel`
and `target-stress` configured for the run, not an independent `uname -r` or
stress-process verification. Stress means the declared artificial-load scenario,
not a threshold on measured CPU usage. The dashboard does not relabel old data
or classify PREEMPT_RT from a kernel version string. Series lacking session
metadata are not silently assigned a kernel/load scenario.

Latency, jitter, counters and controller stages are restricted to the selected
runtime's matching sessions. The controller is associated automatically; no
controller selector is needed. CPU, memory, load and network show the runtime board only;
they are current host metrics, not session-labelled measurements. Multiple
exporter instances with the same board label appear as separate series. For
historical sessions also select their time range. Choosing an old kernel does
not turn current host metrics into that experiment's historical results.
Network panels show each non-loopback interface separately, without an interface selector.

Technical variables are hidden from the filter bar. In dashboard settings →
Variables, configure `datasource` at installation, restrict `stand` when needed,
and set the constant `freshness_seconds` (default `60`) longer than group duration
plus scraping overhead. `stand` defaults to `All`, which also matches a missing
label on a local collector. On a central collector, restrict the hidden stand
selection to distinguish machines of the same board type. These settings do not
change measurement configuration. Options and session membership use metadata
within the selected time range, including metadata no longer active at its end.

The scrape-label contract matches the stand runner:

| Endpoint | Required labels |
| --- | --- |
| Supervisor trace | `board=<runtime board>`, `role="supervisor"` |
| Controller trace | `board=<controller board>`, `role="controller"` |
| Runtime node_exporter | `board=<runtime board>`, `role="runtime"` (also accepts `supervisor`) |
| Arduino receiver | `arduino_session_info` with `session_id`, `kernel`, `stress`; health job `arduino_latency` |

For multi-stand collectors, use a consistent `stand` label across all endpoints
of each stand. Local runner configs use external labels only for remote delivery,
so leave the hidden `stand` at `All` locally. Legacy scrape examples lacking `board` or
`role` must add those labels before using this dashboard. Trace exporters must
expose `rt_trace_stage_latest_us`, `rt_trace_stage_latest_group_index` and
`rt_trace_stage_latest_timestamp_seconds`; receiver integrity panels require the
new group counters and receipt timestamp. Missing series are not zero results.

Trace `avg` covers recorded stage samples, not the Arduino worst tail.
`runtime_wait` includes PLC polling/scheduling, and controller waiting overlaps
runtime work. Hidden `freshness_seconds` hides retained latency/stage gauges
after that age; it does not remove Prometheus history or change measurement
deadlines, and is not an explicit measurement-running signal.

## Laboratory two-board monitoring

The sibling `beremiz-stand` checkout provides `scripts/run_observed_session.py`
for a finite Arduino session with matching controller/supervisor trace metadata.
The lab assets in this repository are
`prometheus/repka5-k3-local.yml` and
`grafana/dashboards/repka5-k3.json`. Unlike the standalone
example above, this setup uses the existing PC Prometheus `:9090` and Grafana
`:3000`, not another managed server pair.

- Node exporters are scraped directly at each board's `:9100`, trace exporters
  at `:9201`; only receiver `:9101` is local to the PC. Provide valid forward and
  return IP routes. In the lab, two narrow Wi-Fi host routes override the VPN
  default for these destinations. SSH tunnels and ProxyJump are not required.
  Scraped `board` and `role` labels distinguish boards with identical hostnames.
- Receiver `:9101` exports the whole-group mean, worst-tail statistics, RMS
  jitter, latest-group integrity and per-session request/response/timeout totals.
- Set receiver `node-exporter-board` to the runtime board label when enriching
  SQLite with CPU/memory; otherwise a legacy unfiltered query can mix boards.
- `receiver.py --start --exit-on-stop --keep-metrics` closes Arduino after the
  finite session but retains the HTTP endpoint. `arduino_last_group_timestamp_seconds`
  distinguishes retained results from active acquisition. Trace exporters expose
  the corresponding `rt_trace_stage_latest_timestamp_seconds` per stage.
- The dashboard hides live latency/stage lines after 15 seconds without a new
  group. Historical data remain in Prometheus. Endpoint UP does not imply active
  pulses, and the counters retain earlier losses even if the last group was good.
- Board clocks must agree with the collector before capture. The session helper
  refuses offsets larger than five seconds; durations still use each board's
  local clock domain. Trace stages are wall-clock buckets, **not process CPU time**,
  and waiting buckets from different boards overlap.

The lab now uses only `rt-stand-observed-session` for measurements; the two
former tunnel units are disabled. Restarting the session service performs a
controlled stack restart and a new finite capture; it does not enable GPIO pulses
automatically at login. The dashboard starts with full-width end-to-end latency
and RMS jitter, followed by individual stage charts with session and min/avg/max
selection. These statistics describe each group, not an overall session mean.
Select the experiment's time range as well as its session. Raw trace files are
per-run and are reinitialized by stack startup: preserve them before starting
another run if required. SQLite and the existing Prometheus TSDB are not erased.
