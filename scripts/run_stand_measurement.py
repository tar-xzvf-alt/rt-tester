#!/usr/bin/env python3
"""Run a complete rt stand measurement from one config file."""

from __future__ import annotations

import argparse
import configparser
import json
import os
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PC_RECEIVER_DIR = ROOT / "src" / "pc-receiver"


def q(value: str | os.PathLike[str]) -> str:
    return shlex.quote(str(value))


def die(message: str) -> None:
    raise SystemExit(f"error: {message}")


def load_config(path: Path) -> configparser.ConfigParser:
    if not path.exists():
        die(f"config not found: {path}")
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.optionxform = str.lower
    with path.open("r", encoding="utf-8") as config_file:
        cfg.read_file(config_file)
    return cfg


def require(cfg: configparser.ConfigParser, section: str, key: str) -> str:
    if not cfg.has_option(section, key):
        die(f"missing [{section}] {key}")
    value = cfg.get(section, key).strip()
    if not value:
        die(f"empty [{section}] {key}")
    return value


def optional(cfg: configparser.ConfigParser, section: str, key: str,
             default: str) -> str:
    if cfg.has_option(section, key):
        return cfg.get(section, key).strip()
    return default


def config_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "on", "true", "yes")


def run(cmd: list[str], *, cwd: Path | None = None, dry_run: bool = False,
        check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    printable = " ".join(q(part) for part in cmd)
    if cwd:
        printable = f"(cd {q(cwd)} && {printable})"
    print(f"$ {printable}")
    sys.stdout.flush()
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def ssh(host: str, command: str, *, dry_run: bool = False,
        capture: bool = False, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        ["ssh", "-o", "BatchMode=yes", host, command],
        dry_run=dry_run,
        capture=capture,
        check=check,
    )


def http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.URLError):
        return False


def write_receiver_config(path: Path, cfg: configparser.ConfigParser,
                          db_path: str, groups: int) -> None:
    measurement = cfg["measurement"]
    measurements_per_group = clamped_measurements_per_group(cfg)
    prometheus_url = optional(
        cfg, "observability", "prometheus-url",
        f"http://127.0.0.1:{optional(cfg, 'observability', 'prometheus-port', '9091')}")
    content = "\n".join([
        f"db = {db_path}",
        f"measurements-per-group = {measurements_per_group}",
        f"measurement-interval-us = {measurement.get('measurement-interval-us')}",
        f"auto-stop-groups = {groups}",
        f"target-board = {measurement.get('target-board')}",
        f"target-kernel = {measurement.get('target-kernel')}",
        f"target-stress = {measurement.get('target-stress')}",
        f"target-payload = {measurement.get('target-payload')}",
        f"prometheus-url = {prometheus_url}",
        "",
    ])
    path.write_text(content, encoding="utf-8")


def clamped_measurements_per_group(cfg: configparser.ConfigParser) -> int:
    value = int(require(cfg, "measurement", "measurements-per-group"))
    return max(1, min(1500, value))


def runtime_stress_enabled(cfg: configparser.ConfigParser) -> bool:
    return config_bool(optional(cfg, "measurement", "target-stress", "off"))


def write_prometheus_config(path: Path, cfg: configparser.ConfigParser) -> None:
    receiver_port = int(optional(cfg, "observability", "receiver-port", "9101"))
    supervisor_target = require(cfg, "supervisor", "trace-target")
    controller_target = require(cfg, "controller", "trace-target")
    supervisor_board = require(cfg, "supervisor", "board")
    controller_board = require(cfg, "controller", "board")
    supervisor_host = require(cfg, "supervisor", "host").split("@")[-1]
    runtime_node_target = optional(cfg, "observability",
                                   "runtime-node-exporter-target",
                                   f"{supervisor_host}:9100")
    content = f"""global:
  scrape_interval: 500ms
  evaluation_interval: 15s
  external_labels:
    monitor: 'rt-stand'

scrape_configs:
  - job_name: 'arduino_latency'
    scrape_interval: 500ms
    static_configs:
      - targets: ['127.0.0.1:{receiver_port}']
        labels:
          source: 'pc-receiver'

  - job_name: 'rt_trace_supervisor'
    scrape_interval: 500ms
    static_configs:
      - targets: ['{supervisor_target}']
        labels:
          board: '{supervisor_board}'
          role: 'supervisor'
          source: 'rt-trace-exporter'

  - job_name: 'rt_trace_controller'
    scrape_interval: 500ms
    static_configs:
      - targets: ['{controller_target}']
        labels:
          board: '{controller_board}'
          role: 'controller'
          source: 'rt-trace-exporter'

  - job_name: 'runtime_node_exporter'
    scrape_interval: 1s
    static_configs:
      - targets: ['{runtime_node_target}']
        labels:
          board: '{supervisor_board}'
          role: 'runtime'
          source: 'node-exporter'
"""
    path.write_text(content, encoding="utf-8")


def start_prometheus(cfg: configparser.ConfigParser, *, dry_run: bool) -> str | None:
    port = int(optional(cfg, "observability", "prometheus-port", "9091"))
    url = f"http://127.0.0.1:{port}"
    if http_ok(f"{url}/-/healthy"):
        print(f"Prometheus already healthy: {url}")
        return url

    binary = optional(cfg, "observability", "prometheus", "prometheus")
    resolved = shutil.which(binary) if "/" not in binary else binary
    if not resolved:
        print("warning: prometheus binary not found; Grafana live datasource will not start")
        return None

    config_path = Path(require(cfg, "observability", "prometheus-config"))
    data_path = Path(require(cfg, "observability", "prometheus-data"))
    log_path = Path(require(cfg, "observability", "prometheus-log"))
    pid_path = Path(require(cfg, "observability", "prometheus-pid"))
    write_prometheus_config(config_path, cfg)
    if dry_run:
        print(f"would start Prometheus on {url}")
        return url
    data_path.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("ab")
    proc = subprocess.Popen([
        resolved,
        f"--config.file={config_path}",
        f"--web.listen-address=127.0.0.1:{port}",
        f"--storage.tsdb.path={data_path}",
        "--storage.tsdb.retention.time=6h",
    ], stdout=log_file, stderr=subprocess.STDOUT)
    pid_path.write_text(f"{proc.pid}\n", encoding="utf-8")
    for _ in range(20):
        if http_ok(f"{url}/-/healthy"):
            print(f"Prometheus started: {url}")
            return url
        time.sleep(0.25)
    print(f"warning: Prometheus did not become healthy; see {log_path}")
    return url


def transport_env(cfg: configparser.ConfigParser) -> str:
    items = []
    if cfg.has_option("transport", "packet-batch-size"):
        items.append(
            f"RT_PACKET_BATCH_SIZE={q(cfg.get('transport', 'packet-batch-size'))}"
        )
    if cfg.has_option("transport", "packet-batch-gap-us"):
        items.append(
            f"RT_PACKET_BATCH_GAP_US={q(cfg.get('transport', 'packet-batch-gap-us'))}"
        )
    if cfg.has_option("transport", "payload-size"):
        items.append(
            f"RT_TRANSPORT_PAYLOAD_SIZE={q(cfg.get('transport', 'payload-size'))}"
        )
    if cfg.has_option("transport", "response-timeout-ms"):
        items.append(
            f"RT_RESPONSE_TIMEOUT_MS={q(cfg.get('transport', 'response-timeout-ms'))}"
        )
    if cfg.has_option("transport", "retransmit-timeout-ms"):
        items.append(
            f"RT_RETRANSMIT_TIMEOUT_MS={q(cfg.get('transport', 'retransmit-timeout-ms'))}"
        )
    if cfg.has_option("transport", "gap-nack-retries"):
        items.append(
            f"RT_GAP_NACK_RETRIES={q(cfg.get('transport', 'gap-nack-retries'))}"
        )
    return " ".join(items)


def start_grafana(cfg: configparser.ConfigParser, *, dry_run: bool) -> str | None:
    port = int(optional(cfg, "observability", "grafana-port", "3001"))
    dashboard_url = optional(cfg, "observability", "grafana-url", "")
    base_url = f"http://127.0.0.1:{port}"
    if http_ok(f"{base_url}/api/health"):
        print(f"Grafana already healthy: {base_url}")
        return dashboard_url or base_url

    binary = optional(cfg, "observability", "grafana", "grafana-server")
    resolved = shutil.which(binary) if "/" not in binary else binary
    if not resolved:
        print("warning: grafana-server binary not found; dashboard will not start")
        return dashboard_url or None

    data_path = Path(require(cfg, "observability", "grafana-data"))
    log_path = Path(require(cfg, "observability", "grafana-log"))
    pid_path = Path(require(cfg, "observability", "grafana-pid"))
    provisioning = ROOT / "grafana" / "provisioning"
    plugins_path = data_path / "plugins"
    logs_path = data_path / "logs"

    if dry_run:
        print(f"would start Grafana on {base_url}")
        return dashboard_url or base_url

    data_path.mkdir(parents=True, exist_ok=True)
    plugins_path.mkdir(parents=True, exist_ok=True)
    logs_path.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("ab")
    proc = subprocess.Popen([
        resolved,
        "--homepath=/usr/share/grafana",
        f"--pidfile={pid_path}",
        f"cfg:server.http_addr=127.0.0.1",
        f"cfg:server.http_port={port}",
        "cfg:auth.anonymous.enabled=true",
        "cfg:auth.anonymous.org_role=Viewer",
        "cfg:auth.disable_login_form=true",
        f"cfg:paths.data={data_path}",
        f"cfg:paths.logs={logs_path}",
        f"cfg:paths.plugins={plugins_path}",
        f"cfg:paths.provisioning={provisioning}",
    ], stdout=log_file, stderr=subprocess.STDOUT)
    for _ in range(40):
        if http_ok(f"{base_url}/api/health"):
            print(f"Grafana started: {base_url}")
            return dashboard_url or base_url
        time.sleep(0.25)
    print(f"warning: Grafana did not become healthy; see {log_path}")
    return dashboard_url or base_url


def stop_pidfile(pid_path: Path, *, dry_run: bool) -> None:
    if not pid_path.exists():
        return
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except ValueError:
        return
    print(f"stopping pid {pid} from {pid_path}")
    if dry_run:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def stop_observability(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    pid_path = Path(require(cfg, "observability", "prometheus-pid"))
    stop_pidfile(pid_path, dry_run=dry_run)
    if cfg.has_option("observability", "grafana-pid"):
        stop_pidfile(Path(require(cfg, "observability", "grafana-pid")),
                     dry_run=dry_run)
    for section in ("supervisor", "controller"):
        host = require(cfg, section, "host")
        exporter_pid = require(cfg, section, "trace-exporter-pid")
        ssh(host,
            f"if [ -f {q(exporter_pid)} ]; then "
            f"kill $(cat {q(exporter_pid)}) 2>/dev/null || true; fi",
            dry_run=dry_run, check=False)


def check_prerequisites(cfg: configparser.ConfigParser, *, dry_run: bool,
                        skip_network: bool, skip_time_sync: bool) -> None:
    for command in ("ssh", "python3"):
        if not shutil.which(command):
            die(f"missing local command: {command}")

    network_check = optional(cfg, "pc", "network-check", "")
    if network_check and not skip_network:
        run([network_check], dry_run=dry_run)

    if not skip_time_sync:
        sync_target_clocks(cfg, dry_run=dry_run)

    for section in ("supervisor", "controller"):
        host = require(cfg, section, "host")
        repo = require(cfg, section, "repo")
        stand_config = require(cfg, section, "stand-config")
        ssh(host, "hostname >/dev/null", dry_run=dry_run)
        ssh(host, f"cd {q(repo)} && scripts/preflight_stand.sh {q(stand_config)}",
            dry_run=dry_run)

    if runtime_stress_enabled(cfg):
        supervisor_host = require(cfg, "supervisor", "host")
        ssh(supervisor_host, "command -v stress-ng >/dev/null",
            dry_run=dry_run)


def sync_target_clocks(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    timestamp = int(time.time())
    seen: set[str] = set()
    for section in ("supervisor", "controller"):
        host = require(cfg, section, "host")
        if host in seen:
            continue
        seen.add(host)
        ssh(host, f"date -u -s '@{timestamp}' >/dev/null",
            dry_run=dry_run)
        print(f"{host} time synchronized")


def stop_local_receivers(*, dry_run: bool) -> None:
    matches: list[tuple[int, str]] = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            raw = (proc / "cmdline").read_bytes()
        except OSError:
            continue
        if not raw:
            continue
        argv = [part.decode(errors="replace") for part in raw.split(b"\0") if part]
        if any(Path(arg).name == "receiver.py" for arg in argv):
            matches.append((int(proc.name), " ".join(argv)))

    if not matches:
        return
    for pid, cmdline in matches:
        print(f"Stopping stale receiver.py pid={pid}: {cmdline}")
        if not dry_run:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    if dry_run:
        return

    deadline = time.monotonic() + 3.0
    alive = {pid for pid, _ in matches}
    while alive and time.monotonic() < deadline:
        for pid in list(alive):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                alive.discard(pid)
        if alive:
            time.sleep(0.1)

    for pid in alive:
        print(f"Killing stale receiver.py pid={pid}")
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def cleanup_before_run(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    stop_local_receivers(dry_run=dry_run)

    supervisor_host = require(cfg, "supervisor", "host")
    supervisor_pid = require(cfg, "supervisor", "pid-path")
    supervisor_trace_pid = require(cfg, "supervisor", "trace-exporter-pid")
    stress_pid = optional(cfg, "stress", "runtime-pid", "/tmp/rt-runtime-stress.pid")
    supervisor_cmd = (
        f"if [ -f {q(supervisor_pid)} ]; then "
        f"kill $(cat {q(supervisor_pid)}) 2>/dev/null || true; "
        f"rm -f {q(supervisor_pid)}; fi; "
        f"pkill -x alt-rt-supervis 2>/dev/null || true; "
        f"pkill -KILL -x runtime 2>/dev/null || true; "
        f"pkill -f '[B]eremiz_service.py' 2>/dev/null || true; "
        f"if [ -f {q(stress_pid)} ]; then "
        f"kill $(cat {q(stress_pid)}) 2>/dev/null || true; "
        f"rm -f {q(stress_pid)}; fi; "
        f"pkill -x stress-ng 2>/dev/null || true; "
        f"if [ -f {q(supervisor_trace_pid)} ]; then "
        f"kill $(cat {q(supervisor_trace_pid)}) 2>/dev/null || true; "
        f"rm -f {q(supervisor_trace_pid)}; fi; "
        f"pkill -f '[t]race_exporter.py' 2>/dev/null || true; "
        f"rm -f /dev/shm/shmem_input /dev/shm/shmem_output"
    )
    ssh(supervisor_host, supervisor_cmd, dry_run=dry_run, check=False)

    controller_host = require(cfg, "controller", "host")
    controller_pid = require(cfg, "controller", "pid-path")
    controller_trace_pid = require(cfg, "controller", "trace-exporter-pid")
    controller_cmd = (
        f"if [ -f {q(controller_pid)} ]; then "
        f"kill $(cat {q(controller_pid)}) 2>/dev/null || true; "
        f"rm -f {q(controller_pid)}; fi; "
        f"pkill -KILL -x controller-emu 2>/dev/null || true; "
        f"if [ -f {q(controller_trace_pid)} ]; then "
        f"kill $(cat {q(controller_trace_pid)}) 2>/dev/null || true; "
        f"rm -f {q(controller_trace_pid)}; fi; "
        f"pkill -f '[t]race_exporter.py' 2>/dev/null || true"
    )
    ssh(controller_host, controller_cmd, dry_run=dry_run, check=False)


def build_remote(cfg: configparser.ConfigParser, section: str, *, dry_run: bool) -> None:
    host = require(cfg, section, "host")
    repo = require(cfg, section, "repo")
    build = require(cfg, section, "build")
    board = require(cfg, section, "board")
    ssh(host,
        f"cd {q(repo)} && cmake -B {q(build)} -DBOARD={q(board)} && "
        f"cmake --build {q(build)}",
        dry_run=dry_run)


def stand_binary(cfg: configparser.ConfigParser, section: str, name: str) -> str:
    binary = optional(cfg, section, "binary", "")
    if binary:
        return binary
    repo = require(cfg, section, "repo")
    build = require(cfg, section, "build")
    return f"{repo}/{build}/src/{name}"


def start_trace_exporter(cfg: configparser.ConfigParser, section: str,
                         *, dry_run: bool) -> None:
    host = require(cfg, section, "host")
    repo = require(cfg, section, "repo")
    port = int(optional(cfg, "observability", "trace-exporter-port", "9201"))
    trace_path = require(cfg, section, "trace-path")
    log_path = require(cfg, section, "trace-exporter-log")
    pid_path = require(cfg, section, "trace-exporter-pid")
    command = (
        f"cd {q(repo)} || exit 1; "
        f"if [ -f {q(pid_path)} ]; then "
        f"kill $(cat {q(pid_path)}) 2>/dev/null || true; fi; "
        f": > {q(trace_path)}; "
        f"python3 scripts/trace_exporter.py --listen 0.0.0.0 "
        f"--port {port} {q(trace_path)} > {q(log_path)} 2>&1 & "
        f"echo $! > {q(pid_path)}"
    )
    ssh(host, command, dry_run=dry_run)


def start_supervisor(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    host = require(cfg, "supervisor", "host")
    repo = require(cfg, "supervisor", "repo")
    iface = require(cfg, "supervisor", "iface")
    runtime = require(cfg, "supervisor", "runtime")
    timeout_us = require(cfg, "supervisor", "timeout-us")
    trace_path = require(cfg, "supervisor", "trace-path")
    log_path = require(cfg, "supervisor", "log-path")
    pid_path = require(cfg, "supervisor", "pid-path")
    stand_config = require(cfg, "supervisor", "stand-config")
    binary = stand_binary(cfg, "supervisor", "alt-rt-supervisor")
    env = transport_env(cfg)
    if env:
        env += " "
    command = (
        f"pkill -x alt-rt-supervis 2>/dev/null || true; "
        f"pkill -x runtime 2>/dev/null || true; "
        f"pkill -f '[B]eremiz_service.py' 2>/dev/null || true; "
        f"rm -f /dev/shm/shmem_input /dev/shm/shmem_output; "
        f": > {q(trace_path)}; : > {q(log_path)}; "
        f"cd {q(repo)} || exit 1; "
        f"{env}RT_TRACE_PATH={q(trace_path)} {q(binary)} -i {q(iface)} "
        f"-t {q(timeout_us)} -r {q(runtime)} > {q(log_path)} 2>&1 & "
        f"echo $! > {q(pid_path)}; "
        f"sleep 2; scripts/pin_stand.sh {q(stand_config)} >/tmp/pin-supervisor.log 2>&1 || true"
    )
    ssh(host, command, dry_run=dry_run)


def start_controller(cfg: configparser.ConfigParser, session_id: int,
                     *, dry_run: bool) -> None:
    host = require(cfg, "controller", "host")
    repo = require(cfg, "controller", "repo")
    iface = require(cfg, "controller", "iface")
    board = require(cfg, "controller", "board")
    trace_path = require(cfg, "controller", "trace-path")
    log_path = require(cfg, "controller", "log-path")
    pid_path = require(cfg, "controller", "pid-path")
    stand_config = require(cfg, "controller", "stand-config")
    measurements_per_group = clamped_measurements_per_group(cfg)
    binary = stand_binary(cfg, "controller", "controller-emu")
    env = transport_env(cfg)
    if env:
        env += " "
    command = (
        f"pkill -x controller-emu 2>/dev/null || true; "
        f": > {q(trace_path)}; : > {q(log_path)}; "
        f"cd {q(repo)} || exit 1; "
        f"{env}RT_TRACE_PATH={q(trace_path)} "
        f"RT_TRACE_SESSION_ID={session_id} "
        f"RT_TRACE_MEASUREMENTS_PER_GROUP={q(measurements_per_group)} "
        f"{q(binary)} -i {q(iface)} -b {q(board)} > {q(log_path)} 2>&1 & "
        f"echo $! > {q(pid_path)}; "
        f"sleep 2; scripts/pin_stand.sh {q(stand_config)} >/tmp/pin-controller.log 2>&1 || true"
    )
    ssh(host, command, dry_run=dry_run)


def start_runtime_stress(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    if not runtime_stress_enabled(cfg):
        print("Runtime stress: off")
        return

    host = require(cfg, "supervisor", "host")
    stress_cmd = optional(
        cfg, "stress", "runtime-command",
        "stress-ng --cpu 0 --vm 0 --vm-bytes 85% --timeout 0",
    )
    pid_path = optional(cfg, "stress", "runtime-pid", "/tmp/rt-runtime-stress.pid")
    log_path = optional(cfg, "stress", "runtime-log", "/tmp/rt-runtime-stress.log")
    command = (
        f"if [ -f {q(pid_path)} ]; then "
        f"old=$(cat {q(pid_path)} 2>/dev/null || true); "
        f"if [ -n \"$old\" ]; then kill $old 2>/dev/null || true; fi; "
        f"rm -f {q(pid_path)}; fi; "
        f"pkill -x stress-ng 2>/dev/null || true; "
        f": > {q(log_path)}; "
        f"{stress_cmd} > {q(log_path)} 2>&1 & "
        f"echo $! > {q(pid_path)}"
    )
    print(f"Runtime stress: on ({stress_cmd})")
    ssh(host, command, dry_run=dry_run)


def stop_runtime_stress(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    if not runtime_stress_enabled(cfg):
        return

    host = require(cfg, "supervisor", "host")
    pid_path = optional(cfg, "stress", "runtime-pid", "/tmp/rt-runtime-stress.pid")
    command = (
        f"if [ -f {q(pid_path)} ]; then "
        f"pid=$(cat {q(pid_path)} 2>/dev/null || true); "
        f"if [ -n \"$pid\" ]; then kill $pid 2>/dev/null || true; fi; "
        f"rm -f {q(pid_path)}; fi; "
        f"pkill -x stress-ng 2>/dev/null || true"
    )
    ssh(host, command, dry_run=dry_run, check=False)


def collect_network_snapshot(cfg: configparser.ConfigParser, section: str,
                             *, dry_run: bool) -> dict[str, object] | None:
    host = require(cfg, section, "host")
    iface = require(cfg, section, "iface")
    if dry_run:
        print(f"would collect network counters from {section} {host}:{iface}")
        return None

    script = f"""
import json
import subprocess

iface = {iface!r}
snapshot = {{"iface": iface, "dev": {{}}, "softnet": {{}}, "ethtool": {{}}}}

keys = [
    "rx_bytes", "rx_packets", "rx_errs", "rx_drop", "rx_fifo",
    "rx_frame", "rx_compressed", "rx_multicast", "tx_bytes",
    "tx_packets", "tx_errs", "tx_drop", "tx_fifo", "tx_colls",
    "tx_carrier", "tx_compressed",
]
try:
    with open("/proc/net/dev", "r", encoding="utf-8") as dev_file:
        for line in dev_file:
            if line.strip().startswith(iface + ":"):
                parts = line.replace(":", " ").split()
                snapshot["dev"] = {{
                    key: int(value) for key, value in zip(keys, parts[1:])
                }}
                break
except OSError:
    pass

softnet = {{"processed": 0, "dropped": 0, "time_squeeze": 0}}
try:
    with open("/proc/net/softnet_stat", "r", encoding="utf-8") as stat_file:
        for line in stat_file:
            fields = line.split()
            if len(fields) >= 3:
                softnet["processed"] += int(fields[0], 16)
                softnet["dropped"] += int(fields[1], 16)
                softnet["time_squeeze"] += int(fields[2], 16)
    snapshot["softnet"] = softnet
except OSError:
    pass

try:
    proc = subprocess.run(["ethtool", "-S", iface], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          check=False)
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            if ":" not in line:
                continue
            key, value = line.strip().split(":", 1)
            value = value.strip()
            if value.isdigit():
                snapshot["ethtool"][key] = int(value)
except (OSError, ValueError):
    pass

print(json.dumps(snapshot, sort_keys=True))
"""
    result = ssh(host, "python3 - <<'PY'\n" + script + "PY",
                 capture=True, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        print(f"warning: failed to collect network counters from {section}")
        if result.stdout:
            print(result.stdout.strip())
        return None
    try:
        snapshot = json.loads(result.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        print(f"warning: invalid network counter snapshot from {section}")
        print(result.stdout.strip())
        return None
    snapshot["section"] = section
    snapshot["host"] = host
    return snapshot


def collect_network_snapshots(cfg: configparser.ConfigParser, *, dry_run: bool
                              ) -> dict[str, dict[str, object]]:
    snapshots: dict[str, dict[str, object]] = {}
    for section in ("supervisor", "controller"):
        snapshot = collect_network_snapshot(cfg, section, dry_run=dry_run)
        if snapshot is not None:
            snapshots[section] = snapshot
    return snapshots


def counter_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    delta: dict[str, int] = {}
    for key in sorted(set(before) | set(after)):
        delta[key] = int(after.get(key, 0)) - int(before.get(key, 0))
    return delta


def print_network_delta(before: dict[str, dict[str, object]] | None,
                        after: dict[str, dict[str, object]] | None) -> bool:
    if not before or not after:
        return True

    ok = True
    anomaly_names = (
        "err", "drop", "crc", "overflow", "underflow", "missed", "lost",
        "fifo", "coll", "carrier", "squeeze",
    )
    print("Network counter delta:")
    for section in ("supervisor", "controller"):
        if section not in before or section not in after:
            continue
        current = after[section]
        dev_delta = counter_delta(
            before[section].get("dev", {}), current.get("dev", {}))
        softnet_delta = counter_delta(
            before[section].get("softnet", {}), current.get("softnet", {}))
        ethtool_delta = counter_delta(
            before[section].get("ethtool", {}), current.get("ethtool", {}))

        print(
            f"  {section} {current.get('host')} {current.get('iface')}: "
            f"rx_packets={dev_delta.get('rx_packets', 0)} "
            f"tx_packets={dev_delta.get('tx_packets', 0)} "
            f"rx_bytes={dev_delta.get('rx_bytes', 0)} "
            f"tx_bytes={dev_delta.get('tx_bytes', 0)}"
        )

        anomalies = {
            f"dev.{key}": value for key, value in dev_delta.items()
            if value and any(name in key for name in anomaly_names)
        }
        anomalies.update({
            f"softnet.{key}": value for key, value in softnet_delta.items()
            if value and key in ("dropped", "time_squeeze")
        })
        anomalies.update({
            f"ethtool.{key}": value for key, value in ethtool_delta.items()
            if value and any(name in key for name in anomaly_names)
        })

        if anomalies:
            ok = False
            for key, value in sorted(anomalies.items()):
                print(f"    {key}: +{value}")
        else:
            print("    no network error/drop counter growth")
    return ok


def stop_targets(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    supervisor_host = require(cfg, "supervisor", "host")
    supervisor_pid = require(cfg, "supervisor", "pid-path")
    controller_host = require(cfg, "controller", "host")
    controller_pid = require(cfg, "controller", "pid-path")
    ssh(supervisor_host,
        f"kill $(cat {q(supervisor_pid)}) 2>/dev/null || true; "
        f"sleep 1; pkill -KILL -x runtime 2>/dev/null || true; "
        f"pkill -f '[B]eremiz_service.py' 2>/dev/null || true",
        dry_run=dry_run, check=False)
    ssh(controller_host,
        f"kill $(cat {q(controller_pid)}) 2>/dev/null || true; sleep 1; "
        f"pkill -KILL -x controller-emu 2>/dev/null || true",
        dry_run=dry_run, check=False)
    stop_runtime_stress(cfg, dry_run=dry_run)


def run_receiver(cfg: configparser.ConfigParser, session_id: int,
                 receiver_config: Path, groups: int, *, dry_run: bool) -> None:
    cmd = [
        "python3", "-u", "receiver.py",
        "--params", str(receiver_config),
        "--session-id", str(session_id),
        "--groups", str(groups),
        "--start",
        "--exit-on-stop",
    ]
    run(cmd, cwd=PC_RECEIVER_DIR, dry_run=dry_run)


def import_trace_metrics(db_path: str, session_id: int, prometheus_url: str | None,
                         *, dry_run: bool) -> None:
    if not prometheus_url:
        return
    time.sleep(1.5)
    run([
        "python3", "import_trace_metrics.py", db_path, str(session_id),
        "--prometheus-url", prometheus_url,
    ], cwd=PC_RECEIVER_DIR, dry_run=dry_run, check=False)


def print_db_summary(db_path: str, session_id: int, expected_groups: int) -> bool:
    if not Path(db_path).exists():
        print(f"warning: database not found: {db_path}")
        return False
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "select count(*), min(group_index), max(group_index), "
            "sum(measurements_per_group) from groups where session_id=?",
            (session_id,),
        )
        groups = cur.fetchone()
        cur.execute(
            "select count(*), min(latency_us), avg(latency_us), max(latency_us) "
            "from latencies where group_id in "
            "(select id from groups where session_id=?)",
            (session_id,),
        )
        latencies = cur.fetchone()
        cur.execute(
            "select event_type, count(*) from events where session_id=? "
            "group by event_type order by event_type",
            (session_id,),
        )
        events = cur.fetchall()

    ok = True
    group_count, first_group, last_group, total_measurements = groups
    latency_count = latencies[0]
    event_types = {event_type for event_type, _ in events}

    if group_count != expected_groups or first_group != 0 or last_group != expected_groups - 1:
        ok = False
    if total_measurements is None or total_measurements < expected_groups:
        ok = False
    if not {"start", "stop"}.issubset(event_types):
        ok = False
    if event_types - {"start", "stop"}:
        ok = False
    if latency_count is None or latency_count <= 0:
        ok = False

    print("SQLite summary:")
    print(f"  groups: {groups}")
    print(f"  latencies: {latencies}")
    print(f"  events: {events}")
    if not ok:
        print("warning: measurement database contains anomalies")
    return ok


def check_latency_trace_consistency(db_path: str, session_id: int) -> bool:
    if not Path(db_path).exists():
        return True

    path_stages = (
        "gpio_to_send",
        "request_send",
        "response_wait",
        "retry_wait",
        "retry_no_response",
        "retry_partial_response",
        "ethernet_recv",
        "runtime_wait",
        "ethernet_send",
        "response_recv",
        "response_to_gpio",
    )
    placeholders = ",".join("?" for _ in path_stages)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "select count(*), max(latency_us) from latencies where group_id in "
            "(select id from groups where session_id=?)",
            (session_id,),
        )
        latency_count, arduino_max_us = cur.fetchone()
        cur.execute(
            f"""
            select host, stage, min(min_us), avg(avg_us), max(max_us)
            from trace_group_metrics
            where session_id = ? and stage in ({placeholders})
            group by host, stage
            order by host, stage
            """,
            (session_id, *path_stages),
        )
        trace_rows = cur.fetchall()

    if not latency_count or arduino_max_us is None or not trace_rows:
        return True

    # If one mandatory trace stage is already longer than Arduino's full-path
    # max latency, the Arduino input is likely seeing a different signal.
    threshold_us = max(arduino_max_us * 1.5, arduino_max_us + 1000.0)
    contradictions = [
        row for row in trace_rows
        if row[2] is not None and row[2] > threshold_us
    ]
    if not contradictions:
        return True

    print("warning: Arduino latency contradicts imported trace metrics")
    print(f"  Arduino max latency: {arduino_max_us:.0f} us")
    for host, stage, min_us, avg_us, max_us in contradictions:
        print(
            f"  trace {host}/{stage}: min={min_us:.0f} us, "
            f"avg={avg_us:.0f} us, max={max_us:.0f} us"
        )
    print(
        "  Check wiring/loopback: Arduino D7 -> controller GPIO input, "
        "controller GPIO output -> Arduino D20, and common GND."
    )
    return False


def check_trace_group_alignment(db_path: str, session_id: int,
                                expected_groups: int) -> bool:
    if not Path(db_path).exists():
        return True

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            select host, count(distinct group_index), min(group_index),
                   max(group_index)
            from trace_group_metrics
            where session_id = ?
            group by host
            order by host
            """,
            (session_id,),
        )
        rows = cur.fetchall()

    if not rows:
        return True

    mismatches = []
    for host, group_count, first_group, last_group in rows:
        if (group_count != expected_groups or first_group != 0 or
                last_group != expected_groups - 1):
            mismatches.append((host, group_count, first_group, last_group))

    if not mismatches:
        return True

    print("warning: trace group count does not match receiver groups")
    print(f"  receiver groups: 0..{expected_groups - 1} ({expected_groups})")
    for host, group_count, first_group, last_group in mismatches:
        print(
            f"  trace {host}: groups {first_group}..{last_group} "
            f"({group_count})"
        )
    print(
        "  This usually means controller GPIO input saw extra edges or trace "
        "started before the Arduino measurement window."
    )
    return False


def print_trace_counts(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    for section in ("supervisor", "controller"):
        host = require(cfg, section, "host")
        trace_path = require(cfg, section, "trace-path")
        result = ssh(host, f"wc -l {q(trace_path)} 2>/dev/null || true",
                     dry_run=dry_run, capture=True, check=False)
        if not dry_run and result.stdout:
            print(f"{section} trace: {result.stdout.strip()}")


def print_target_log_summary(cfg: configparser.ConfigParser, *, dry_run: bool) -> bool:
    ok = True
    pattern = "ERR|WARN|timeout|wrong crc|didn.t respond"
    for section in ("supervisor", "controller"):
        host = require(cfg, section, "host")
        log_path = require(cfg, section, "log-path")
        command = f"grep -Ec {q(pattern)} {q(log_path)} 2>/dev/null || true"
        result = ssh(host, command, dry_run=dry_run, capture=True, check=False)
        if dry_run:
            continue
        count_text = (result.stdout or "0").strip().splitlines()[-1]
        try:
            count = int(count_text)
        except ValueError:
            count = 0
        print(f"{section} log anomaly count: {count}")
        if count > 0:
            ok = False
    return ok


def run_measurement(args: argparse.Namespace) -> None:
    cfg = load_config(Path(args.config))
    stand_name = require(cfg, "stand", "name")
    session_id = args.session_id or int(time.time())
    groups = args.groups or int(require(cfg, "measurement", "groups"))
    db_path = args.db or require(cfg, "measurement", "db")

    print(f"Stand: {stand_name}")
    print(f"Session ID: {session_id}")
    print(f"Groups: {groups}")
    measurements_per_group = clamped_measurements_per_group(cfg)
    interval_us = int(require(cfg, "measurement", "measurement-interval-us"))
    duration_s = groups * measurements_per_group * interval_us / 1_000_000
    print(f"Measurements per group: {measurements_per_group}")
    print(f"Expected measurement time: {duration_s:.1f}s")
    sys.stdout.flush()

    if args.stop_observability:
        stop_observability(cfg, dry_run=args.dry_run)
        return

    check_prerequisites(cfg, dry_run=args.dry_run,
                        skip_network=args.skip_pc_network_check,
                        skip_time_sync=args.skip_time_sync)

    if args.build:
        build_remote(cfg, "supervisor", dry_run=args.dry_run)
        build_remote(cfg, "controller", dry_run=args.dry_run)

    cleanup_before_run(cfg, dry_run=args.dry_run)

    start_trace_exporter(cfg, "supervisor", dry_run=args.dry_run)
    start_trace_exporter(cfg, "controller", dry_run=args.dry_run)
    prometheus_url = None if args.no_prometheus else start_prometheus(
        cfg, dry_run=args.dry_run)
    grafana_url = None if args.no_grafana else start_grafana(
        cfg, dry_run=args.dry_run)

    receiver_config = Path(tempfile.gettempdir()) / f"rt-stand-{stand_name}-{session_id}.conf"
    write_receiver_config(receiver_config, cfg, db_path, groups)
    print(f"Receiver config: {receiver_config}")

    network_before = None
    network_after = None
    try:
        start_runtime_stress(cfg, dry_run=args.dry_run)
        start_supervisor(cfg, dry_run=args.dry_run)
        start_controller(cfg, session_id, dry_run=args.dry_run)
        network_before = collect_network_snapshots(cfg, dry_run=args.dry_run)
        run_receiver(cfg, session_id, receiver_config, groups,
                     dry_run=args.dry_run)
    finally:
        if network_before is not None:
            network_after = collect_network_snapshots(cfg, dry_run=args.dry_run)
        if not args.keep_targets:
            stop_targets(cfg, dry_run=args.dry_run)

    import_trace_metrics(db_path, session_id, prometheus_url,
                         dry_run=args.dry_run)
    db_ok = True
    if not args.dry_run:
        db_ok = print_db_summary(db_path, session_id, groups)
        db_ok = check_trace_group_alignment(db_path, session_id, groups) and db_ok
        db_ok = check_latency_trace_consistency(db_path, session_id) and db_ok
    print_trace_counts(cfg, dry_run=args.dry_run)
    logs_ok = print_target_log_summary(cfg, dry_run=args.dry_run)
    network_ok = print_network_delta(network_before, network_after)

    if prometheus_url:
        print(f"Prometheus: {prometheus_url}")
    if grafana_url:
        print(f"Grafana: {grafana_url}?var-session_id={session_id}")
    if db_ok and logs_ok and network_ok:
        print("Measurement completed successfully")
    else:
        print("Measurement completed with anomalies")
        raise SystemExit(2)


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True,
                        help="stand config file")
    parser.add_argument("--session-id", type=int,
                        help="fixed session ID; default is current Unix time")
    parser.add_argument("--groups", type=int,
                        help="override measurement group count")
    parser.add_argument("--db", help="override SQLite database path")
    parser.add_argument("--build", action="store_true",
                        help="build remote supervisor/controller trees before run")
    parser.add_argument("--keep-targets", action="store_true",
                        help="do not stop supervisor/controller after measurement")
    parser.add_argument("--no-prometheus", action="store_true",
                        help="do not start local Prometheus")
    parser.add_argument("--no-grafana", action="store_true",
                        help="do not start local Grafana")
    parser.add_argument("--skip-pc-network-check", action="store_true",
                        help="skip PC-side network check")
    parser.add_argument("--skip-time-sync", action="store_true",
                        help="do not set target board clocks from this host")
    parser.add_argument("--stop-observability", action="store_true",
                        help="stop Prometheus and remote trace exporters from config")
    parser.add_argument("--dry-run", action="store_true",
                        help="print commands without executing them")
    args = parser.parse_args()
    if args.groups is not None and args.groups < 1:
        parser.error("--groups must be >= 1")
    if args.session_id is not None and args.session_id < 1:
        parser.error("--session-id must be >= 1")
    run_measurement(args)


if __name__ == "__main__":
    main()
