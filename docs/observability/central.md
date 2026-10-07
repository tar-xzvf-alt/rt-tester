# Central Prometheus and Grafana

[Русский](../ru/observability/central.md)

The PC receiver and target exporters are on private measurement networks. Local
Prometheus scrapes them and sends live time series to **your** central Prometheus
through SSH forwarding. Server Grafana queries that central store.

```text
Arduino → PC receiver :9101 ─┐
target node_exporter :9100 ─┼→ PC Prometheus :9092 → remote_write → SSH :19090
optional trace exporters ──┘                                   │
                                     server Prometheus 127.0.0.1:9090
                                                              │
                                     server Grafana 127.0.0.1:3000
                                                              │ SSH forward
                                          PC browser 127.0.0.1:3002
```

Local Prometheus remains necessary: receiver queries its API for SoC metrics,
and supervised runs import trace aggregates after collection. Remote write does
**not** publish the SQLite session database, raw traces, or experiment notes.
For a simpler PC-only setup see [local observability](local.md).

## 1. Prepare your server

Install a Prometheus version supporting `--web.enable-remote-write-receiver`,
Grafana, and SSH server using your distribution's packages. On ALT Linux, if the
configured repositories provide them:

```bash
apt-get install prometheus grafana openssh-server
```

Check installed units and options (`systemctl cat prometheus`, `prometheus --help`)
before changing service configuration. Service names, environment-file locations,
and package availability are installation-specific. The runner expects the
server destinations **127.0.0.1:9090** and **127.0.0.1:3000**; these destinations
are fixed in its SSH forwarding code.

Configure central Prometheus with a writable persistent TSDB and these options:

```text
--config.file=/etc/prometheus/prometheus.yml
--storage.tsdb.path=/var/lib/prometheus
--storage.tsdb.retention.time=365d
--web.listen-address=127.0.0.1:9090
--web.enable-remote-write-receiver
```

365 days is an example retention policy; size it for your collectors and disk.
An ALT service may read `OPTIONS` from a sysconfig file; confirm the unit actually
uses it. Minimal server configuration:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: ['127.0.0.1:9090']
```

Use the package's service account and writable storage permissions. Validate with
`promtool check config /etc/prometheus/prometheus.yml`, restart/enable the actual
service, then on the server check:

```bash
curl -fsS http://127.0.0.1:9090/-/ready
curl -fsS http://127.0.0.1:9090/api/v1/status/flags
```

The flags response must show the remote-write receiver enabled. Readiness alone
does not prove write acceptance. Keep the write endpoint reachable through SSH;
the example does not require public unauthenticated ingestion.

Configure Grafana to listen on `127.0.0.1:3000` using its `[server] http_addr`
and `http_port` settings. Provision these Prometheus datasources in the installed
Grafana provisioning directory:

```yaml
apiVersion: 1
datasources:
  - name: RT GPIO Prometheus
    uid: rt-gpio-prometheus
    type: prometheus
    access: proxy
    url: http://127.0.0.1:9090
    jsonData:
      timeInterval: 500ms
  - name: RT Trace Prometheus
    uid: rt-trace-prometheus
    type: prometheus
    access: proxy
    url: http://127.0.0.1:9090
    jsonData:
      timeInterval: 500ms
```

Copy the desired dashboard JSON from installed
`/usr/share/rt-tester-tools/grafana/dashboards/` on the PC (or the source checkout)
to a readable server dashboard directory such as `/var/lib/grafana/dashboards`.
Provision a file provider:

```yaml
apiVersion: 1
providers:
  - name: RT Tester Dashboards
    orgId: 1
    folder: RT Tester
    type: file
    options:
      path: /var/lib/grafana/dashboards
```

Restart the actual Grafana service, verify its logs and
`curl -fsS http://127.0.0.1:3000/api/health`, then verify the datasources in its UI.
The existing `configs/server/wetgrape-*` assets record the project deployment
and provide examples; they are not an installation script for your server. In
particular, do not assume its broad service sandbox override is required on yours.

## 2. Configure SSH forwarding

Create a server account and authorize a PC key for noninteractive forwarding.
It does not need access to TSDB files. An example restricted `authorized_keys`
entry permits only the two required destinations:

```text
restrict,port-forwarding,command="/bin/false",permitopen="127.0.0.1:9090",permitopen="127.0.0.1:3000" ssh-ed25519 YOUR_PUBLIC_KEY
```

Server SSH policy must allow local forwarding. Set the account, SSH port, and
identity in the reader-owned profile. Check host-key trust and authentication
before collection. For an independent forwarding check from the PC:

```bash
ssh -N -T -o BatchMode=yes -o ExitOnForwardFailure=yes \
  -i ~/.ssh/rt-observability -p 22 \
  -L 127.0.0.1:19090:127.0.0.1:9090 \
  -L 127.0.0.1:3002:127.0.0.1:3000 prometheus-writer@CENTRAL_HOST
```

In another terminal query `http://127.0.0.1:19090/-/ready` and
`http://127.0.0.1:3002/api/health`. Stop this manual tunnel before starting a
runner-managed tunnel so the ports are free.

## 3. Adapt and run the central profile

Copy the installed example into your saved experiment directory:

```text
/usr/share/rt-tester-tools/configs/stands/examples/visionfive2-gpio-central.conf
```

Edit `root@TARGET_HOST`, metadata, hardware configuration, and central transport;
confirm Arduino serial discovery/access separately:

```ini
[observability]
collector-label = my-measurement-pc
prometheus-port = 9092
receiver-port = 9101
remote-write-url = http://127.0.0.1:19090/api/v1/write
central-ssh-host = prometheus-writer@CENTRAL_HOST
central-ssh-port = 22
central-ssh-identity = ~/.ssh/rt-observability
central-prometheus-local-port = 19090
central-grafana-local-port = 3002
central-tunnel-pid = .rt-tester-example/central-tunnel.pid
central-tunnel-log = .rt-tester-example/central-tunnel.log
grafana-managed = false
grafana-url = http://127.0.0.1:3002/d/rt-standalone-gpio
```

Keep the complete example's other fields and use the absolute paths prepared in
the walkthrough; the INI snippet shows template paths before adaptation.
The runner starts a single SSH process
with both forwards and checks central readiness. It starts local Prometheus, not
local Grafana. Run after completing the physical stand preparation:

```bash
rt-tester-run-gpio --config ./visionfive2-gpio-central.conf --groups 10
```

Supervised stands use the same transport fields but their mode-specific local
Prometheus/jobs and `rt-trace-stages` dashboard. Do not copy a standalone scrape
configuration into a supervised profile.

## 4. Verify each hop during collection

1. **Receiver:** `http://127.0.0.1:9101/metrics` contains
   `arduino_latency_mean`, `arduino_latency_avg`, and `arduino_jitter` after a
   completed group. `avg` is tail mean; `mean` and jitter cover all received
   responses. Before the first group the response can be empty.
2. **Local scrape:** open `http://127.0.0.1:9092/targets`. During collection,
   `up{job="arduino_latency"}` and `up{job="runtime_node_exporter"}` should be `1`.
   Query `arduino_latency_avg{session_id="SESSION_ID"}` at
   `http://127.0.0.1:9092/graph` (the query page; newer versions may redirect).
   After receiver exits, its `up` can become `0`;
   use a time range covering collection.
3. **Write queue:** inspect local `http://127.0.0.1:9092/metrics` and Prometheus log.
   If the self-metrics are scraped, use
   `prometheus_remote_storage_samples_pending` and
   `rate(prometheus_remote_storage_samples_failed_total[5m])` to diagnose backlog
   or failures. Metric names vary with Prometheus version; an absent series does
   not prove success, and the generated runner config does not add a self-scrape.
4. **Central receipt:** at `http://127.0.0.1:19090/graph`, query:

   ```promql
   arduino_latency_avg{collector="my-measurement-pc",session_id="SESSION_ID"}
   up{job="runtime_node_exporter",collector="my-measurement-pc"}
   count by (collector, stand) (arduino_session_info)
   ```

   The stable HTTP query API can also verify delivery from the PC:

   ```bash
   curl -fsSG http://127.0.0.1:19090/api/v1/query \
     --data-urlencode 'query=arduino_latency_avg{collector="my-measurement-pc",session_id="SESSION_ID"}'
   ```

   Successful receipt of the matching session is the delivery test. A healthy
   tunnel without data is insufficient. For a completed run select its time range
   or use `max_over_time(arduino_latency_avg{session_id="SESSION_ID"}[1h])`.
5. **Dashboard:** open
   `http://127.0.0.1:3002/d/rt-standalone-gpio?var-session_id=SESSION_ID`, select the
   board/session and a time range containing collection, and confirm latency,
   jitter, and load. If empty, use Grafana Explore against `rt-gpio-prometheus`
   with the central query above and check datasource UID/provisioning before
   changing the measurement.

The runner generates `monitor`, `collector`, and `stand` as **external labels**.
They are attached to remotely delivered series, **not stored as labels on local
scraped series**. Do not filter local queries by `collector` or `stand`; use
session/board locally. Set distinct collector and stand values across PCs/stands
to distinguish central series. Existing dashboards primarily select board/session;
use Explore with collector/stand filters when diagnosing multiple collectors.

The exported receiver gauges describe the latest completed group. Remote write
does not guarantee an archived sample for every Arduino group, especially for
short runs. Retain and validate SQLite independently.

## 5. Stop managed monitoring and preserve evidence

Use the same profile and saved experiment directory:

```bash
rt-tester-run-gpio --config ./visionfive2-gpio-central.conf --stop-observability
# For a supervised profile:
rt-tester-run-stand --config ./supervised.conf --stop-observability
```

Allow the queue to drain and verify central receipt before stopping local
Prometheus/tunnel. This stops runner-managed processes, not server services.
Archive the database and profile through your own artifact workflow. Cyclictest
uses [bundle publication](../usage/publish-cyclictest.md), independently of
Prometheus. The [validation record](../reference/validation.md) distinguishes
documentation checks from server/hardware walkthroughs actually executed.
