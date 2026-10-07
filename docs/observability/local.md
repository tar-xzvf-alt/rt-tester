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
