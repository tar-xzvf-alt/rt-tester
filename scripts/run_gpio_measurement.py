#!/usr/bin/env python3
"""Run a standalone GPIO measurement with rt-handler and receiver.py."""

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
import urllib.parse
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


def prometheus_query(prometheus_url: str, query: str) -> str | None:
    url = f"{prometheus_url}/api/v1/query?{urllib.parse.urlencode({'query': query})}"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    if payload.get("status") != "success":
        return None
    result = payload.get("data", {}).get("result", [])
    if not result:
        return "0"
    value = result[0].get("value", [None, None])[1]
    return str(value) if value is not None else None


def clamped_measurements_per_group(cfg: configparser.ConfigParser) -> int:
    value = int(require(cfg, "measurement", "measurements-per-group"))
    return max(1, min(1500, value))


def write_receiver_config(path: Path, cfg: configparser.ConfigParser,
                          db_path: str, groups: int) -> None:
    measurement = cfg["measurement"]
    prometheus_url = optional(
        cfg, "observability", "prometheus-url",
        f"http://127.0.0.1:{optional(cfg, 'observability', 'prometheus-port', '9092')}")
    content = "\n".join([
        f"db = {db_path}",
        f"measurements-per-group = {clamped_measurements_per_group(cfg)}",
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


def write_prometheus_config(path: Path, cfg: configparser.ConfigParser) -> None:
    receiver_port = int(optional(cfg, "observability", "receiver-port", "9101"))
    target_host = require(cfg, "target", "host").split("@")[-1]
    node_target = optional(
        cfg, "observability", "node-exporter-target", f"{target_host}:9100")
    board = optional(cfg, "target", "label", require(cfg, "target", "board"))
    content = f"""global:
  scrape_interval: 500ms
  evaluation_interval: 15s
  external_labels:
    monitor: 'rt-gpio-stand'

scrape_configs:
  - job_name: 'arduino_latency'
    scrape_interval: 500ms
    static_configs:
      - targets: ['127.0.0.1:{receiver_port}']
        labels:
          source: 'pc-receiver'

  - job_name: 'runtime_node_exporter'
    scrape_interval: 1s
    static_configs:
      - targets: ['{node_target}']
        labels:
          board: '{board}'
          role: 'standalone-gpio'
          source: 'node-exporter'
"""
    path.write_text(content, encoding="utf-8")


def start_prometheus(cfg: configparser.ConfigParser, *, dry_run: bool) -> str | None:
    port = int(optional(cfg, "observability", "prometheus-port", "9092"))
    url = f"http://127.0.0.1:{port}"
    pid_path = Path(require(cfg, "observability", "prometheus-pid"))
    if http_ok(f"{url}/-/healthy"):
        if pid_path.exists():
            print(f"Restarting managed Prometheus on {url}")
            stop_prometheus(cfg, dry_run=dry_run)
            if not dry_run:
                time.sleep(1)
        else:
            print(f"Prometheus already healthy: {url}")
            return url

    binary = optional(cfg, "observability", "prometheus", "prometheus")
    resolved = shutil.which(binary) if "/" not in binary else binary
    if not resolved:
        print("warning: prometheus binary not found; SoC metrics will be absent")
        return None

    config_path = Path(require(cfg, "observability", "prometheus-config"))
    data_path = Path(require(cfg, "observability", "prometheus-data"))
    log_path = Path(require(cfg, "observability", "prometheus-log"))
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
    return None


def write_grafana_provisioning(path: Path, cfg: configparser.ConfigParser,
                               prometheus_url: str) -> Path:
    dashboards_dir = ROOT / "grafana" / "dashboards"
    datasource_dir = path / "datasources"
    dashboard_dir = path / "dashboards"
    datasource_dir.mkdir(parents=True, exist_ok=True)
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    (datasource_dir / "rt-gpio-prometheus.yml").write_text(f"""apiVersion: 1

datasources:
  - name: RT GPIO Prometheus
    uid: rt-gpio-prometheus
    type: prometheus
    access: proxy
    url: {prometheus_url}
    isDefault: true
    editable: true
    jsonData:
      timeInterval: 500ms
""", encoding="utf-8")
    (dashboard_dir / "rt-gpio-dashboards.yml").write_text(f"""apiVersion: 1

providers:
  - name: RT GPIO Dashboards
    orgId: 1
    folder: RT GPIO
    type: file
    disableDeletion: false
    updateIntervalSeconds: 5
    allowUiUpdates: true
    options:
      path: {dashboards_dir}
""", encoding="utf-8")
    return path


def start_grafana(cfg: configparser.ConfigParser, *, dry_run: bool,
                  prometheus_url: str) -> str | None:
    port = int(optional(cfg, "observability", "grafana-port", "3002"))
    dashboard_url = optional(
        cfg, "observability", "grafana-url",
        f"http://127.0.0.1:{port}/d/rt-standalone-gpio")
    base_url = f"http://127.0.0.1:{port}"
    pid_path = Path(require(cfg, "observability", "grafana-pid"))
    if http_ok(f"{base_url}/api/health"):
        if pid_path.exists():
            print(f"Restarting managed Grafana on {base_url}")
            stop_grafana(cfg, dry_run=dry_run)
            if not dry_run:
                time.sleep(1)
        else:
            print(f"Grafana already healthy: {base_url}")
            return dashboard_url

    binary = optional(cfg, "observability", "grafana", "grafana-server")
    resolved = shutil.which(binary) if "/" not in binary else binary
    if not resolved:
        print("warning: grafana-server binary not found; dashboard will not start")
        return None

    data_path = Path(require(cfg, "observability", "grafana-data"))
    log_path = Path(require(cfg, "observability", "grafana-log"))
    provisioning = write_grafana_provisioning(
        data_path / "provisioning", cfg, prometheus_url)
    plugins_path = data_path / "plugins"
    logs_path = data_path / "logs"

    if dry_run:
        print(f"would start Grafana on {base_url}")
        return dashboard_url

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
    pid_path.write_text(f"{proc.pid}\n", encoding="utf-8")
    for _ in range(40):
        if http_ok(f"{base_url}/api/health"):
            print(f"Grafana started: {base_url}")
            return dashboard_url
        time.sleep(0.25)
    print(f"warning: Grafana did not become healthy; see {log_path}")
    return dashboard_url


def stop_prometheus(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    pid_path = Path(require(cfg, "observability", "prometheus-pid"))
    if not pid_path.exists():
        return
    pid = pid_path.read_text(encoding="utf-8").strip()
    if not pid:
        pid_path.unlink(missing_ok=True)
        return
    if dry_run:
        print(f"would stop Prometheus pid {pid}")
        return
    try:
        os.kill(int(pid), signal.SIGTERM)
    except (ProcessLookupError, ValueError):
        pass
    pid_path.unlink(missing_ok=True)


def stop_grafana(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    if not cfg.has_option("observability", "grafana-pid"):
        return
    pid_path = Path(require(cfg, "observability", "grafana-pid"))
    if not pid_path.exists():
        return
    pid = pid_path.read_text(encoding="utf-8").strip()
    if not pid:
        pid_path.unlink(missing_ok=True)
        return
    if dry_run:
        print(f"would stop Grafana pid {pid}")
        return
    try:
        os.kill(int(pid), signal.SIGTERM)
    except (ProcessLookupError, ValueError):
        pass
    pid_path.unlink(missing_ok=True)


def stop_local_receivers(*, dry_run: bool) -> None:
    matches: list[tuple[int, str]] = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            raw = (proc / "cmdline").read_bytes()
        except OSError:
            continue
        argv = [part.decode(errors="replace") for part in raw.split(b"\0") if part]
        if any(Path(arg).name == "receiver.py" for arg in argv):
            matches.append((int(proc.name), " ".join(argv)))

    for pid, cmdline in matches:
        print(f"Stopping stale receiver.py pid={pid}: {cmdline}")
        if not dry_run:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def check_prerequisites(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    for command in ("ssh", "rsync"):
        if not shutil.which(command):
            die(f"missing local command: {command}")

    host = require(cfg, "target", "host")
    ssh(host, "hostname >/dev/null", dry_run=dry_run)
    ssh(host, "command -v make >/dev/null && command -v cc >/dev/null",
        dry_run=dry_run)
    ssh(host, "command -v node_exporter >/dev/null || true", dry_run=dry_run,
        check=False)


def check_arduino(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    port = optional(cfg, "measurement", "arduino-port", "")
    baud = int(optional(cfg, "measurement", "arduino-baud", "115200"))
    if dry_run:
        print("would check Arduino serial connection")
        return

    try:
        import serial
        import serial.tools.list_ports
    except ImportError as exc:
        die(f"pyserial is required for Arduino preflight: {exc}")

    if not port:
        candidates = [
            item.device for item in serial.tools.list_ports.comports()
            if "Arduino" in item.description or "ACM" in item.description
        ]
        if not candidates:
            print("Available serial ports:")
            for item in serial.tools.list_ports.comports():
                print(f"  {item.device}: {item.description}")
            die("Arduino serial port was not detected; set [measurement] arduino-port")
        port = candidates[0]

    try:
        ser = serial.Serial(port, baudrate=baud, timeout=1)
        try:
            time.sleep(2)
            ser.reset_input_buffer()
        finally:
            ser.close()
    except Exception as exc:
        die(f"cannot open Arduino serial port {port}: {exc}")
    print(f"Arduino serial preflight OK: {port} @ {baud}")


def sync_target_clock(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    timestamp = int(time.time())
    host = require(cfg, "target", "host")
    ssh(host, f"date -u -s '@{timestamp}' >/dev/null", dry_run=dry_run)
    print(f"{host} time synchronized")


def deploy_handler(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    local = Path(require(cfg, "target", "rt-handler-local"))
    remote = require(cfg, "target", "repo")
    host = require(cfg, "target", "host")
    if not local.exists():
        die(f"rt-handler-local not found: {local}")
    ssh(host, f"mkdir -p {q(remote)}", dry_run=dry_run)
    run([
        "rsync", "-a", "--delete",
        "--exclude", ".git/",
        "--exclude", "__pycache__/",
        "--exclude", "*.o",
        "--exclude", "*-monitor",
        f"{local}/", f"{host}:{remote}/",
    ], dry_run=dry_run)


def build_handler(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    host = require(cfg, "target", "host")
    repo = require(cfg, "target", "repo")
    board = require(cfg, "target", "board")
    command = f"cd {q(repo + '/src')} && make BOARD={q(board)}"
    ssh(host, command, dry_run=dry_run)


def cleanup_target(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    host = require(cfg, "target", "host")
    pid_path = require(cfg, "target", "pid-path")
    binary = Path(require(cfg, "target", "binary")).name
    binary_path = require(cfg, "target", "binary")
    stress_pid = optional(cfg, "stress", "pid", "/tmp/rt-gpio-stress.pid")
    command = (
        f"if [ -f {q(pid_path)} ]; then "
        f"kill $(cat {q(pid_path)}) 2>/dev/null || true; "
        f"rm -f {q(pid_path)}; fi; "
        f"pkill -x {q(binary)} 2>/dev/null || true; "
        f"pkill -f {q(binary_path)} 2>/dev/null || true; "
        f"if [ -f {q(stress_pid)} ]; then "
        f"kill $(cat {q(stress_pid)}) 2>/dev/null || true; "
        f"rm -f {q(stress_pid)}; fi; "
        f"pkill -x stress-ng 2>/dev/null || true"
    )
    ssh(host, command, dry_run=dry_run, check=False)


def start_handler(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    host = require(cfg, "target", "host")
    repo = require(cfg, "target", "repo")
    binary = require(cfg, "target", "binary")
    pid_path = require(cfg, "target", "pid-path")
    stdout_log = require(cfg, "target", "stdout-log")
    metrics_log = optional(cfg, "target", "metrics-log", "/dev/null")
    command = (
        f"mkdir -p {q(Path(stdout_log).parent)}; "
        f": > {q(stdout_log)}; "
        f"cd {q(repo + '/src')} || exit 1; "
        f"{q(binary)} {q(metrics_log)} >{q(stdout_log)} 2>&1 & "
        f"echo $! > {q(pid_path)}; "
        f"sleep 1; "
        f"if ! kill -0 $(cat {q(pid_path)}) 2>/dev/null; then "
        f"echo 'rt-handler failed to start; log follows:' >&2; "
        f"tail -n 80 {q(stdout_log)} >&2; exit 1; fi"
    )
    ssh(host, command, dry_run=dry_run)


def start_stress(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    if not config_bool(optional(cfg, "measurement", "target-stress", "off")):
        print("Target stress: off")
        return
    host = require(cfg, "target", "host")
    stress_cmd = optional(
        cfg, "stress", "command",
        "stress-ng --cpu 0 --vm 0 --vm-bytes 85% --timeout 0",
    )
    pid_path = optional(cfg, "stress", "pid", "/tmp/rt-gpio-stress.pid")
    log_path = optional(cfg, "stress", "log", "/tmp/rt-gpio-stress.log")
    command = (
        f"pkill -x stress-ng 2>/dev/null || true; "
        f": > {q(log_path)}; "
        f"{stress_cmd} >{q(log_path)} 2>&1 & "
        f"echo $! > {q(pid_path)}"
    )
    print(f"Target stress: on ({stress_cmd})")
    ssh(host, command, dry_run=dry_run)


def pin_node_exporter(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    host = require(cfg, "target", "host")
    housekeeping = optional(cfg, "target", "housekeeping-cpus", "0")
    command = (
        "pgrep -x node_exporter 2>/dev/null | while read -r pid; do "
        "ps -L -p \"$pid\" -o tid= | while read -r tid; do "
        "chrt -o -p 0 \"$tid\" 2>/dev/null || true; "
        f"taskset -pc {q(housekeeping)} \"$tid\" >/dev/null 2>&1 || true; "
        "done; done"
    )
    ssh(host, command, dry_run=dry_run, check=False)
    print(f"node_exporter pinned to SCHED_OTHER on CPU(s): {housekeeping}")


def run_receiver(cfg: configparser.ConfigParser, session_id: int,
                 receiver_config: Path, groups: int, *, dry_run: bool) -> None:
    cmd = [
        sys.executable,
        "-u",
        "receiver.py",
        "--params", str(receiver_config),
        "--session-id", str(session_id),
        "--groups", str(groups),
        "--start",
        "--exit-on-stop",
    ]
    port = optional(cfg, "measurement", "arduino-port", "")
    if port:
        cmd.extend(["--port", port])
    run(cmd, cwd=PC_RECEIVER_DIR, dry_run=dry_run)


def print_target_diagnostics(cfg: configparser.ConfigParser,
                             *, dry_run: bool) -> None:
    if dry_run:
        return
    host = require(cfg, "target", "host")
    pid_path = require(cfg, "target", "pid-path")
    stdout_log = require(cfg, "target", "stdout-log")
    command = (
        f"echo '== rt-handler process =='; "
        f"if [ -f {q(pid_path)} ]; then "
        f"pid=$(cat {q(pid_path)} 2>/dev/null || true); "
        f"if [ -n \"$pid\" ]; then ps -fp \"$pid\" || true; "
        f"else echo 'empty pidfile'; fi; "
        f"else echo 'pidfile missing'; fi; "
        f"echo '== node_exporter process =='; "
        f"pgrep -a -x node_exporter 2>/dev/null || echo 'not running'; "
        f"echo '== node_exporter scheduling =='; "
        f"ps -eLo pid,tid,cls,rtprio,psr,comm,args | "
        f"awk '$6 == \"node_exporter\" {{ print }}'; "
        f"echo '== rt-handler log tail =='; "
        f"tail -n 40 {q(stdout_log)} 2>/dev/null || true"
    )
    result = ssh(host, command, capture=True, check=False)
    if result.stdout:
        print("Target diagnostics:")
        print(result.stdout.rstrip())


def print_prometheus_diagnostics(prometheus_url: str | None,
                                 session_id: int) -> None:
    if not prometheus_url:
        return
    queries = (
        ("arduino_latency_avg samples",
         f'sum(count_over_time(arduino_latency_avg{{session_id="{session_id}"}}[30m]))'),
        ("soc_cpu_percent samples",
         f'sum(count_over_time(soc_cpu_percent{{session_id="{session_id}"}}[30m]))'),
        ("runtime_node_exporter up", 'max_over_time(up{job="runtime_node_exporter"}[5m])'),
    )
    print("Prometheus diagnostics:")
    for label, query in queries:
        value = prometheus_query(prometheus_url, query)
        print(f"  {label}: {value if value is not None else 'unavailable'}")


def print_db_summary(db_path: str, session_id: int, expected_groups: int) -> bool:
    if not Path(db_path).exists():
        print(f"warning: database not found: {db_path}")
        return False

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        groups = cur.execute(
            "select count(*), min(group_index), max(group_index) from groups "
            "where session_id=?", (session_id,),
        ).fetchone()
        latencies = cur.execute(
            "select count(*), min(latency_us), avg(latency_us), max(latency_us) "
            "from latencies where group_id in "
            "(select id from groups where session_id=?)", (session_id,),
        ).fetchone()
        soc_count = cur.execute(
            "select count(*) from soc_metrics where session_id=?",
            (session_id,),
        ).fetchone()[0]
        events = cur.execute(
            "select event_type, count(*) from events where session_id=? "
            "group by event_type order by event_type", (session_id,),
        ).fetchall()

    count, first_group, last_group = groups
    print("SQLite summary:")
    print(f"  groups: {groups}")
    print(f"  latencies: {latencies}")
    print(f"  soc_metrics: {soc_count}")
    print(f"  events: {events}")
    return (
        count == expected_groups and first_group == 0 and
        last_group == expected_groups - 1 and (latencies[0] or 0) > 0
    )


def run_measurement(args: argparse.Namespace) -> None:
    cfg = load_config(Path(args.config))
    stand_name = require(cfg, "stand", "name")
    session_id = args.session_id or int(time.time())
    groups = args.groups or int(require(cfg, "measurement", "groups"))
    db_path = args.db or require(cfg, "measurement", "db")

    print(f"Stand: {stand_name}")
    print(f"Session ID: {session_id}")
    print(f"Groups: {groups}")
    print(f"Measurements per group: {clamped_measurements_per_group(cfg)}")
    sys.stdout.flush()

    if args.stop_observability:
        stop_prometheus(cfg, dry_run=args.dry_run)
        stop_grafana(cfg, dry_run=args.dry_run)
        return

    check_prerequisites(cfg, dry_run=args.dry_run)
    check_arduino(cfg, dry_run=args.dry_run)
    if not args.skip_time_sync:
        sync_target_clock(cfg, dry_run=args.dry_run)
    if args.deploy:
        deploy_handler(cfg, dry_run=args.dry_run)
    if args.build:
        build_handler(cfg, dry_run=args.dry_run)
    if args.prepare_only:
        print("GPIO stand preparation completed")
        return

    cleanup_target(cfg, dry_run=args.dry_run)
    stop_local_receivers(dry_run=args.dry_run)
    prometheus_url = None if args.no_prometheus else start_prometheus(
        cfg, dry_run=args.dry_run)
    grafana_url = None
    if prometheus_url and not args.no_grafana:
        grafana_url = start_grafana(
            cfg, dry_run=args.dry_run, prometheus_url=prometheus_url)

    receiver_config = Path(tempfile.gettempdir()) / f"rt-gpio-{stand_name}-{session_id}.conf"
    write_receiver_config(receiver_config, cfg, db_path, groups)
    print(f"Receiver config: {receiver_config}")

    try:
        start_stress(cfg, dry_run=args.dry_run)
        start_handler(cfg, dry_run=args.dry_run)
        pin_node_exporter(cfg, dry_run=args.dry_run)
        run_receiver(cfg, session_id, receiver_config, groups,
                     dry_run=args.dry_run)
    finally:
        print_target_diagnostics(cfg, dry_run=args.dry_run)
        if not args.dry_run:
            print_prometheus_diagnostics(prometheus_url, session_id)
        if not args.keep_target:
            cleanup_target(cfg, dry_run=args.dry_run)

    db_ok = True if args.dry_run else print_db_summary(db_path, session_id, groups)
    if prometheus_url:
        print(f"Prometheus: {prometheus_url}")
    if grafana_url:
        print(f"Grafana: {grafana_url}?var-session_id={session_id}")
    if db_ok:
        print("GPIO measurement completed successfully")
    else:
        print("GPIO measurement completed with anomalies")
        raise SystemExit(2)


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="GPIO stand config file")
    parser.add_argument("--session-id", type=int,
                        help="fixed session ID; default is current Unix time")
    parser.add_argument("--groups", type=int,
                        help="override measurement group count")
    parser.add_argument("--db", help="override SQLite database path")
    parser.add_argument("--deploy", action="store_true",
                        help="rsync rt-handler to the target before run")
    parser.add_argument("--build", action="store_true",
                        help="build rt-handler on the target before run")
    parser.add_argument("--prepare-only", action="store_true",
                        help="run checks/deploy/build and exit before measurement")
    parser.add_argument("--keep-target", action="store_true",
                        help="do not stop rt-handler after measurement")
    parser.add_argument("--no-prometheus", action="store_true",
                        help="do not start local Prometheus")
    parser.add_argument("--no-grafana", action="store_true",
                        help="do not start local Grafana")
    parser.add_argument("--stop-observability", action="store_true",
                        help="stop Prometheus started by this runner")
    parser.add_argument("--skip-time-sync", action="store_true",
                        help="do not set target clock from this host")
    parser.add_argument("--dry-run", action="store_true",
                        help="print commands without executing them")
    args = parser.parse_args()
    run_measurement(args)


if __name__ == "__main__":
    main()
