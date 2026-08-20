# Central Prometheus and Grafana

The measurement endpoints are not reachable from the public server: the
receiver listens on the measurement PC and node/trace exporters are on private
stand networks. Prometheus must therefore scrape them locally and forward the
samples to the central Prometheus with `remote_write`.

The resulting data path is:

```text
Arduino / node_exporter / trace exporters
                    |
                    v
local managed Prometheus (short-term scrape and query buffer)
                    |
                    | remote_write through SSH forwarding
                    v
wetgrape.su Prometheus (long-term TSDB) -> wetgrape.su Grafana
```

The local Prometheus remains necessary because `receiver.py` reads SoC metrics
from its query API and supervised runs import trace aggregates after the
measurement. Local Grafana is not started.

## Stand configuration

Central transport is configured in the `[observability]` section:

```ini
collector-label = measurement-pc
remote-write-url = http://127.0.0.1:19090/api/v1/write
central-ssh-host = prometheus-writer@wetgrape.su
central-ssh-port = 228
central-ssh-identity = ~/.local/share/rt-tester/central_observability_ed25519
central-prometheus-local-port = 19090
central-grafana-local-port = 13000
central-tunnel-pid = ~/.local/state/rt-tester/central-observability-tunnel.pid
central-tunnel-log = ~/.local/state/rt-tester/central-observability-tunnel.log
grafana-managed = false
grafana-url = http://127.0.0.1:13000/d/rt-standalone-gpio
```

Supervised stand configs use the `rt-trace-stages` dashboard instead. The
runner starts one SSH process with two local forwards:

```text
127.0.0.1:19090 -> wetgrape.su 127.0.0.1:9090 (Prometheus)
127.0.0.1:13000 -> wetgrape.su 127.0.0.1:3000 (Grafana)
```

SSH public-key authentication must work non-interactively. Use a dedicated key
and an unprivileged server account whose `authorized_keys` entry only permits
the two required destinations:

```text
restrict,port-forwarding,command="/bin/false",permitopen="127.0.0.1:9090",permitopen="127.0.0.1:3000" ssh-ed25519 ...
```

The restricted account does not need access to Prometheus files or a privileged
group. The runner checks the central Prometheus readiness endpoint before
starting a measurement.

Generated Prometheus configs add `collector` and `stand` external labels, so
sessions from different measurement PCs do not overwrite each other.

Stop local observability and its central tunnel with:

```sh
rt-tester-run-gpio --config CONFIG --stop-observability
rt-tester-run-stand --config CONFIG --stop-observability
```

## Server configuration

Prometheus on the central server listens on `127.0.0.1:9090` and is started
with `--web.enable-remote-write-receiver`. The SSH tunnel is the only ingestion
path; the write endpoint is not exposed without authentication on a public
interface. Server retention is 365 days.

The deployed server files are tracked under `configs/server/`:

```text
wetgrape-prometheus.yml
wetgrape-prometheus.sysconfig
wetgrape-prometheus-override.conf
wetgrape-grafana-datasources.yml
wetgrape-grafana-dashboards.yml
```

Grafana provisions two datasource UIDs against the same central Prometheus:

- `rt-gpio-prometheus` for standalone GPIO dashboards;
- `rt-trace-prometheus` for supervised trace dashboards.

Both existing dashboards are provisioned in the `RT Tester` folder.

## Scope of stored data

Prometheus receives the live time series exported by receiver, node_exporter,
and trace exporters. The complete GPIO/supervised SQLite session database still
remains the source of truth for all configured stored tail samples, integrity
counters, events, and imported trace aggregates. Uploading those SQLite
artifacts is not implemented by Prometheus remote write.

Cyclictest uses a separate workflow: finalized bundles can be published into
the central `rt-results` catalog with `rt-tester-publish-cyclictest`. See
[Publishing Cyclictest](../usage/publish-cyclictest.md). This publisher does not
use Prometheus.
