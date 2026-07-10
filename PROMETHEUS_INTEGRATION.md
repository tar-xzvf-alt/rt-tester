# Prometheus Integration Guide

## Overview

This guide explains how to set up Prometheus and Grafana for monitoring RT latency tests.

## Architecture

```
┌─────────────┐   :9100/metrics    ┌─────────────┐
│   SoC 1     │ ─────────────────► │             │
│  (Radxa)    │   scrape           │             │
└─────────────┘                    │             │
                                   │  Prometheus │ ──► Grafana
┌─────────────┐   :9101/metrics    │   Server    │
│  PC Client  │ ─────────────────► │ (localhost) │   (localhost:3000)
│  (receiver) │   scrape           │             │
└─────────────┘                    └─────────────┘
```

## Components

### 1. SoC Exporter (C code)
- HTTP server on port 9100
- Exposes CPU/memory metrics from SoC
- Requires libmicrohttpd

**Compilation:**
```bash
# Install libmicrohttpd (on target device, legacy C exporter only)
apt-get install libmicrohttpd-devel

# Compile
gcc -pthread -o soc-monitor main.c gpio_handler_*.c metrics_collector.c utils.c log_writer.c prometheus_exporter.c -lgpiod -lrt -lmicrohttpd
```

### 2. PC Metrics Server (Python)
- HTTP server on port 9101
- Exposes Arduino latency metrics
- Part of receiver.py

**Start Prometheus server first:**
```bash
./receiver.py --params measurement.conf
```

### 3. Prometheus Server

**Install:**
```bash
# Download from https://prometheus.io/download/
tar xzf prometheus-*.tar.gz
cd prometheus-*
```

**Run:**
```bash
./prometheus --config.file=../prometheus/prometheus.yml
```

**Configuration (prometheus/prometheus.yml):**
- Retention: 30 days
- Scrapes SoC exporters (9100) and PC client (9101)
- Scrape interval: 15s

### 4. Grafana

**Install:**
```bash
# Download from https://grafana.com/download/
# or: apt-get install grafana
```

**Setup:**
1. Start Grafana: `systemctl start grafana-server` (port 3000)
2. Login: admin/admin
3. Add Prometheus datasource: http://localhost:9090
4. Import dashboard: `grafana/rt-tester-dashboard.json`

### Trace Grafana Dashboard

The trace feature branch also includes a provisioned Grafana dashboard for the
supervised raw-Ethernet trace metrics:

```text
grafana/dashboards/rt-trace-stages.json
grafana/provisioning/datasources/trace-prometheus.yml
grafana/provisioning/dashboards/trace-dashboards.yml
```

The datasource is `RT Trace Prometheus` and points to the local trace Prometheus:

```text
http://127.0.0.1:9091
```

The dashboard is `RT Trace Stage Breakdown`. It combines Arduino latency metrics
from `receiver.py :9101` with trace stage metrics from the RockPI/VisionFive
trace exporters:

- `Average Latency`
- `Maximum Latency`
- `Average Trace Stage Duration`
- `Maximum Trace Stage Duration`

When using the stand helpers, start it with:

```bash
cd /home/taranev/work_repos/beremiz-stand
scripts/start_trace_prometheus_local.sh
scripts/start_trace_grafana_local.sh
```

Then run a trace measurement and open:

```text
http://127.0.0.1:3001/d/rt-trace-stages
```

The dashboard has variables for `session_id`, `board`, `host`, and `stage`.
Choose the `session_id` printed by the receiver/smoke script.

## Metric Names

### SoC Metrics (from C exporter on port 9100)
- `soc_cpu_percent` - Current CPU usage %
- `soc_cpu_max` - Max CPU in current group
- `soc_memory_percent` - Current memory usage %
- `soc_memory_max` - Max memory in current group
- `soc_group_counter` - Current group number

### Latency Metrics (from PC client on port 9101)
- `arduino_latency_avg` - Average latency (worst N)
- `arduino_latency_mean` - Mean latency (all measurements)
- `arduino_latency_min` - Min latency
- `arduino_latency_max` - Max latency
- `arduino_jitter` - RMS jitter
- `arduino_session_info` - Session status

**Labels:**
- `board` - SoC board name (radxa, lichee, etc.)
- `kernel` - Kernel version
- `session_id` - Session identifier
- `stress` - "on" or "off"
- `group` - Group number

## Example PromQL Queries

```promql
# Average latency for a session
avg(arduino_latency_avg{session_id="123456"})

# Max latency across all groups
max(arduino_latency_max{session_id="123456"})

# Jitter trend
rate(arduino_jitter[5m])

# CPU vs Latency correlation
soc_cpu_percent{board="radxa"} + arduino_latency_avg{board="radxa"}

# All sessions for a board
avg by (session_id) (arduino_latency_avg{board="radxa"})
```

## Configuration File Example

```ini
[prometheus]
url = http://localhost:9090

# Legacy SSH [soc] configuration is not used by current receiver runs.
# SoC CPU/memory metrics are collected from node_exporter through Prometheus.

[arduino]
port = /dev/ttyUSB0
baudrate = 115200
```

## Troubleshooting

1. **Check if exporters are reachable:**
```bash
curl http://192.168.1.100:9100/metrics  # SoC
curl http://localhost:9101/metrics       # PC client
```

2. **Check Prometheus targets:**
- Open http://localhost:9090/targets

3. **Query Prometheus directly:**
- Open http://localhost:9090/graph
- Enter PromQL queries

4. **Check Grafana logs:**
```bash
journalctl -u grafana-server -f
```
