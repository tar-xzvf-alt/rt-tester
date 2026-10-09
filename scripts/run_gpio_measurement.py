#!/usr/bin/env python3
"""Run a standalone GPIO measurement with rt-handler and receiver.py."""

from __future__ import annotations

import argparse
import configparser
import contextlib
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

import central_observability
from run_cleanup import REMOTE_CLEANUP_TIMEOUT, final_actions, stop_pidfile_command


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


def execution_mode(cfg: configparser.ConfigParser) -> str:
    mode = optional(cfg, "target", "execution-mode", "userspace")
    if mode not in ("userspace", "kernelspace"):
        die(f"unsupported [target] execution-mode: {mode}")
    return mode


def run(cmd: list[str], *, cwd: Path | None = None, dry_run: bool = False,
        check: bool = True, capture: bool = False,
        timeout: float | None = None) -> subprocess.CompletedProcess[str]:
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
        stderr=None,
        timeout=timeout,
    )


def ssh(host: str, command: str, *, dry_run: bool = False,
        capture: bool = False, check: bool = True,
        timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, command],
        dry_run=dry_run,
        capture=capture,
        check=check,
        timeout=timeout,
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
        f"response-timeout-us = {measurement.get('response-timeout-us', '10000')}",
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
        cfg, "observability", "node-exporter-target", "") or f"{target_host}:9100"
    board = optional(cfg, "target", "label", require(cfg, "target", "board"))
    labels = central_observability.external_labels(cfg, "rt-gpio-stand")
    remote_write = central_observability.remote_write_block(cfg)
    content = f"""global:
  scrape_interval: 500ms
  evaluation_interval: 15s
  external_labels:
{labels}

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
{remote_write}
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
    retention = optional(cfg, "observability", "prometheus-retention-time", "6h")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    write_prometheus_config(config_path, cfg)
    if dry_run:
        print(f"would start Prometheus on {url}")
        return url

    data_path.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("ab")
    proc = subprocess.Popen([
        resolved,
        f"--config.file={config_path}",
        f"--web.listen-address=127.0.0.1:{port}",
        f"--storage.tsdb.path={data_path}",
        f"--storage.tsdb.retention.time={retention}",
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
    if not central_observability.managed_grafana(cfg):
        return central_observability.grafana_url(cfg) or None
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
    log_path.parent.mkdir(parents=True, exist_ok=True)
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


def stop_managed_process(pid_path: Path, name: str, *, dry_run: bool) -> None:
    if not pid_path.exists():
        return
    raw_pid = pid_path.read_text(encoding="utf-8").strip()
    if not raw_pid:
        pid_path.unlink(missing_ok=True)
        return
    if dry_run:
        print(f"would stop {name} pid {raw_pid}")
        return
    try:
        pid = int(raw_pid)
        os.kill(pid, signal.SIGTERM)
        for _ in range(100):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, ValueError, PermissionError):
        pass
    pid_path.unlink(missing_ok=True)


def stop_prometheus(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    pid_path = Path(require(cfg, "observability", "prometheus-pid"))
    stop_managed_process(pid_path, "Prometheus", dry_run=dry_run)


def stop_grafana(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    if not cfg.has_option("observability", "grafana-pid"):
        return
    pid_path = Path(require(cfg, "observability", "grafana-pid"))
    stop_managed_process(pid_path, "Grafana", dry_run=dry_run)


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


def check_prerequisites(cfg: configparser.ConfigParser, *, dry_run: bool,
                        need_deploy: bool, need_build: bool) -> None:
    mode = execution_mode(cfg)
    if mode == "kernelspace" and (need_deploy or need_build):
        die("--deploy/--build are only supported for userspace rt-handler")

    local_commands = ["ssh"]
    if need_deploy:
        local_commands.append("rsync")
    for command in local_commands:
        if not shutil.which(command):
            die(f"missing local command: {command}")

    host = require(cfg, "target", "host")
    ssh(host, "hostname >/dev/null", dry_run=dry_run)
    if mode == "userspace":
        if need_build:
            ssh(host, "command -v make >/dev/null && command -v cc >/dev/null",
                dry_run=dry_run)
        else:
            binary = require(cfg, "target", "binary")
            command = (
                f"case {q(binary)} in */*) test -x {q(binary)} ;; "
                f"*) command -v {q(binary)} >/dev/null ;; esac"
            )
            ssh(host, command, dry_run=dry_run)
    else:
        module = optional(cfg, "target", "module", "rt_gpio_responder")
        ssh(host, f"command -v modprobe >/dev/null && modinfo {q(module)} >/dev/null",
            dry_run=dry_run)

    expected_kernel = optional(cfg, "target", "expected-kernel", "")
    if expected_kernel:
        result = ssh(host, "uname -r", dry_run=dry_run, capture=True)
        if not dry_run and result.stdout.strip() != expected_kernel:
            die(f"target kernel {result.stdout.strip()} does not match "
                f"expected {expected_kernel}")

    remote_commands = ["chrt", "taskset", "node_exporter", "ps", "awk"]
    if config_bool(optional(cfg, "measurement", "target-stress", "off")):
        remote_commands.extend(["stress-ng", "setsid"])
    command = " && ".join(
        f"command -v {q(command)} >/dev/null" for command in remote_commands
    )
    ssh(host, command, dry_run=dry_run)


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
    command = f"cd {q(repo + '/src')} && make clean && make"
    ssh(host, command, dry_run=dry_run)


def cleanup_target(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    """Recover the dedicated target before a run, including stale processes."""
    host = require(cfg, "target", "host")
    stress_pid = optional(cfg, "stress", "pid", "/tmp/rt-gpio-stress.pid")
    commands = [
        "systemctl stop rt-handler 2>/dev/null || true",
        "pkill -x rt-handler 2>/dev/null || true",
    ]
    if cfg.has_option("target", "pid-path"):
        pid_path = require(cfg, "target", "pid-path")
        commands.extend([
            f"if [ -f {q(pid_path)} ]; then kill $(cat {q(pid_path)}) "
            f"2>/dev/null || true; rm -f {q(pid_path)}; fi",
        ])
    module = optional(cfg, "target", "module", "rt_gpio_responder")
    commands.extend([
        f"modprobe -r {q(module)} 2>/dev/null || true",
        f"if [ -f {q(stress_pid)} ]; then "
        f"pid=$(cat {q(stress_pid)}); kill $pid 2>/dev/null || true; "
        "i=0; while kill -0 $pid 2>/dev/null && [ $i -lt 50 ]; do "
        "sleep 0.1; i=$((i + 1)); done; "
        "kill -KILL $pid 2>/dev/null || true; "
        f"rm -f {q(stress_pid)}; fi",
        "pkill -TERM -f '^stress-ng' 2>/dev/null || true",
        "sleep 0.2",
        "pkill -KILL -f '^stress-ng' 2>/dev/null || true",
    ])
    ssh(host, "; ".join(commands), dry_run=dry_run, check=False)


def stop_target(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    """Stop the configured measurement resources, not all processes by name."""
    host = require(cfg, "target", "host")

    def stop_handler() -> None:
        if execution_mode(cfg) == "kernelspace":
            module = optional(cfg, "target", "module", "rt_gpio_responder")
            command = f"if [ -d /sys/module/{q(module)} ]; then modprobe -r {q(module)}; fi"
        else:
            command = stop_pidfile_command(require(cfg, "target", "pid-path"))
        ssh(host, command, dry_run=dry_run, timeout=REMOTE_CLEANUP_TIMEOUT)

    def stop_stress() -> None:
        if config_bool(optional(cfg, "measurement", "target-stress", "off")):
            pid_path = optional(cfg, "stress", "pid", "/tmp/rt-gpio-stress.pid")
            ssh(host, stop_pidfile_command(pid_path, process_group=True), dry_run=dry_run,
                timeout=REMOTE_CLEANUP_TIMEOUT)

    with final_actions(("GPIO handler stop", stop_handler), ("GPIO stress stop", stop_stress)):
        pass


def start_userspace_handler(cfg: configparser.ConfigParser,
                            *, dry_run: bool) -> None:
    host = require(cfg, "target", "host")
    board = require(cfg, "target", "board")
    binary = require(cfg, "target", "binary")
    pid_path = require(cfg, "target", "pid-path")
    stdout_log = require(cfg, "target", "stdout-log")
    workdir = optional(cfg, "target", "workdir", "/")
    handler_args = optional(cfg, "target", "args", "-b {board}").format(
        board=q(board),
    )
    command = (
        f"mkdir -p {q(Path(stdout_log).parent)}; "
        f": > {q(stdout_log)}; "
        f"cd {q(workdir)} || exit 1; "
        f"{q(binary)} {handler_args} >{q(stdout_log)} 2>&1 & "
        f"echo $! > {q(pid_path)}; "
        f"sleep 1; "
        f"if ! kill -0 $(cat {q(pid_path)}) 2>/dev/null; then "
        f"echo 'rt-handler failed to start; log follows:' >&2; "
        f"tail -n 80 {q(stdout_log)} >&2; exit 1; fi"
    )
    ssh(host, command, dry_run=dry_run)


def start_kernel_handler(cfg: configparser.ConfigParser,
                         *, dry_run: bool) -> None:
    host = require(cfg, "target", "host")
    module = optional(cfg, "target", "module", "rt_gpio_responder")
    module_args = optional(
        cfg, "target", "module-args", "board=starfive log_events=0")
    command = (
        f"modprobe {q(module)} {module_args}; sleep 1; "
        f"test -d /sys/module/{q(module)}; "
        f"grep -q {q(optional(cfg, 'target', 'irq-name', 'rt-gpio-responder'))} "
        f"/proc/interrupts"
    )
    ssh(host, command, dry_run=dry_run)


def start_handler(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    if execution_mode(cfg) == "kernelspace":
        start_kernel_handler(cfg, dry_run=dry_run)
    else:
        start_userspace_handler(cfg, dry_run=dry_run)


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
        f": > {q(log_path)}; "
        f"setsid sh -c {q('exec ' + stress_cmd)} >{q(log_path)} 2>&1 & "
        f"echo $! > {q(pid_path)}"
    )
    print(f"Target stress: on ({stress_cmd})")
    ssh(host, command, dry_run=dry_run)


def warm_up_stress(cfg: configparser.ConfigParser, seconds: int,
                   *, dry_run: bool) -> None:
    if seconds <= 0 or not config_bool(
            optional(cfg, "measurement", "target-stress", "off")):
        return
    print(f"Stress warm-up: {seconds} seconds")
    if not dry_run:
        time.sleep(seconds)

    host = require(cfg, "target", "host")
    sample_count = int(optional(cfg, "stress", "stability-samples", "6"))
    sample_interval = int(optional(cfg, "stress", "stability-interval-seconds", "5"))
    max_spread = float(optional(cfg, "stress", "memory-stability-percent", "5"))
    samples = []
    for index in range(sample_count):
        result = ssh(
            host,
            "awk '/MemAvailable:/ { print $2 }' /proc/meminfo",
            dry_run=dry_run,
            capture=True,
        )
        if dry_run:
            continue
        samples.append(int(result.stdout.strip()))
        if index + 1 < sample_count:
            time.sleep(sample_interval)
    if samples:
        spread = 100 * (max(samples) - min(samples)) / max(samples)
        print(f"Stress memory stability: spread={spread:.2f}%")
        if spread > max_spread:
            die(
                f"stress memory did not stabilize: {spread:.2f}% > "
                f"{max_spread:.2f}%"
            )


def pin_node_exporter(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    host = require(cfg, "target", "host")
    housekeeping = optional(cfg, "target", "housekeeping-cpus", "0")
    command = (
        "set -eu; pids=$(pgrep -x node_exporter); test -n \"$pids\"; "
        "for pid in $pids; do for task in /proc/$pid/task/*; do "
        "tid=${task##*/}; "
        "chrt -o -p 0 \"$tid\"; "
        f"taskset -pc {q(housekeeping)} \"$tid\" >/dev/null; "
        "done; done"
    )
    ssh(host, command, dry_run=dry_run)
    print(f"node_exporter pinned to SCHED_OTHER on CPU(s): {housekeeping}")


def pin_handler(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    host = require(cfg, "target", "host")
    rt_cpu = optional(cfg, "target", "rt-cpu", "1")
    irq_priority = int(optional(cfg, "target", "gpio-irq-priority", "99"))
    irq_name = require(cfg, "target", "irq-name")
    commands = []

    if execution_mode(cfg) == "userspace":
        pid_path = require(cfg, "target", "pid-path")
        handler_priority = int(optional(
            cfg, "target", "handler-priority", "85"))
        commands.extend([
            f"pid=$(cat {q(pid_path)}); test -d /proc/$pid",
            "for task in /proc/$pid/task/*; do tid=${task##*/}; "
            f"chrt -f -p {handler_priority} $tid; "
            f"taskset -pc {q(rt_cpu)} $tid >/dev/null; done",
        ])

    commands.extend([
        f"irq=$(awk -v name={q(irq_name)} '$0 ~ name "
        "{ gsub(\":\", \"\", $1); print $1; exit }' /proc/interrupts)",
        "test -n \"$irq\"",
        "tid=$(ps -eLo tid=,comm= | awk -v prefix=\"irq/$irq-\" "
        "'index($2, prefix) == 1 { print $1; exit }')",
        "test -n \"$tid\"",
        f"chrt -f -p {irq_priority} $tid",
        f"taskset -pc {q(rt_cpu)} $tid >/dev/null",
        "ps -p $tid -o pid=,tid=,cls=,rtprio=,psr=,comm=",
    ])
    ssh(host, "set -eu; " + "; ".join(commands), dry_run=dry_run)
    print(f"Handler path pinned to CPU {rt_cpu}; GPIO IRQ FIFO {irq_priority}")


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
    if execution_mode(cfg) == "kernelspace":
        module = optional(cfg, "target", "module", "rt_gpio_responder")
        handler_diagnostics = (
            "echo '== kernel handler =='; "
            f"lsmod | grep -w '^{module}' || true; "
            f"grep {q(require(cfg, 'target', 'irq-name'))} /proc/interrupts || true; "
            "echo '== kernel log =='; "
            "journalctl -k -n 30 --no-pager 2>/dev/null || dmesg | tail -n 30"
        )
    else:
        pid_path = require(cfg, "target", "pid-path")
        stdout_log = require(cfg, "target", "stdout-log")
        handler_diagnostics = (
            "echo '== rt-handler process =='; "
            f"if [ -f {q(pid_path)} ]; then "
            f"pid=$(cat {q(pid_path)} 2>/dev/null || true); "
            f"if [ -n \"$pid\" ]; then ps -fp \"$pid\" || true; "
            "else echo 'empty pidfile'; fi; "
            "else echo 'pidfile missing'; fi; "
            "echo '== rt-handler log tail =='; "
            f"tail -n 40 {q(stdout_log)} 2>/dev/null || true"
        )
    command = (
        handler_diagnostics + "; "
        f"echo '== node_exporter process =='; "
        f"pgrep -a -x node_exporter 2>/dev/null || echo 'not running'; "
        f"echo '== node_exporter scheduling =='; "
        f"ps -eLo pid,tid,cls,rtprio,psr,comm,args | "
        f"awk '$6 == \"node_exporter\" {{ print }}'"
    )
    result = ssh(host, command, capture=True, check=False, timeout=REMOTE_CLEANUP_TIMEOUT)
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

    with contextlib.closing(sqlite3.connect(db_path)) as conn:
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
        integrity = cur.execute(
            "select coalesce(sum(measurements_per_group),0), "
            "coalesce(sum(requests_sent),0), "
            "coalesce(sum(responses_received),0), "
            "coalesce(sum(timeout_count),0), "
            "sum(case when requests_sent != measurements_per_group or "
            "responses_received != requests_sent or timeout_count != 0 "
            "then 1 else 0 end) from groups where session_id=?",
            (session_id,),
        ).fetchone()

    count, first_group, last_group = groups
    print("SQLite summary:")
    print(f"  groups: {groups}")
    print(f"  latencies: {latencies}")
    print(f"  soc_metrics: {soc_count}")
    print(f"  events: {events}")
    print(
        "  integrity (expected, requests, responses, timeouts, bad groups): "
        f"{integrity}"
    )
    expected_measurements = integrity[0]
    return (
        count == expected_groups and first_group == 0 and
        last_group == expected_groups - 1 and (latencies[0] or 0) > 0 and
        integrity == (
            expected_measurements, expected_measurements,
            expected_measurements, 0, 0,
        )
    )


def run_measurement(args: argparse.Namespace) -> None:
    cfg = load_config(Path(args.config))
    stand_name = require(cfg, "stand", "name")
    session_id = args.session_id or int(time.time())
    groups = args.groups or int(require(cfg, "measurement", "groups"))
    db_path = str(Path(os.path.expandvars(
        args.db or require(cfg, "measurement", "db"))).expanduser().resolve())
    warmup_seconds = args.warmup_seconds
    if warmup_seconds is None:
        warmup_seconds = int(optional(cfg, "stress", "warmup-seconds", "0"))

    print(f"Stand: {stand_name}")
    print(f"Session ID: {session_id}")
    print(f"Groups: {groups}")
    print(f"Measurements per group: {clamped_measurements_per_group(cfg)}")
    print(f"Execution mode: {execution_mode(cfg)}")
    sys.stdout.flush()

    if args.stop_observability:
        stop_prometheus(cfg, dry_run=args.dry_run)
        stop_grafana(cfg, dry_run=args.dry_run)
        central_observability.stop_tunnel(cfg, dry_run=args.dry_run)
        return

    check_prerequisites(
        cfg, dry_run=args.dry_run,
        need_deploy=args.deploy, need_build=args.build,
    )
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
    if not args.no_prometheus or not args.no_grafana:
        central_observability.start_tunnel(cfg, dry_run=args.dry_run)
    prometheus_url = None if args.no_prometheus else start_prometheus(
        cfg, dry_run=args.dry_run)
    grafana_url = None
    if prometheus_url and not args.no_grafana:
        grafana_url = start_grafana(
            cfg, dry_run=args.dry_run, prometheus_url=prometheus_url)

    if prometheus_url:
        print(f"Prometheus: {prometheus_url}")
    if grafana_url:
        print(f"Grafana: {grafana_url}?var-session_id={session_id}")

    receiver_config = Path(tempfile.gettempdir()) / f"rt-gpio-{stand_name}-{session_id}.conf"
    if not args.dry_run:
        Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    write_receiver_config(receiver_config, cfg, db_path, groups)
    print(f"Receiver config: {receiver_config}")

    actions = [
        ("target diagnostics", lambda: print_target_diagnostics(cfg, dry_run=args.dry_run)),
    ]
    if not args.dry_run:
        actions.append(("Prometheus diagnostics",
                        lambda: print_prometheus_diagnostics(prometheus_url, session_id)))
    if not args.keep_target:
        actions.append(("target cleanup", lambda: stop_target(cfg, dry_run=args.dry_run)))
    with final_actions(*actions):
        start_stress(cfg, dry_run=args.dry_run)
        pin_node_exporter(cfg, dry_run=args.dry_run)
        warm_up_stress(cfg, warmup_seconds, dry_run=args.dry_run)
        start_handler(cfg, dry_run=args.dry_run)
        pin_handler(cfg, dry_run=args.dry_run)
        run_receiver(cfg, session_id, receiver_config, groups,
                     dry_run=args.dry_run)

    db_ok = True if args.dry_run else print_db_summary(db_path, session_id, groups)
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
    parser.add_argument("--warmup-seconds", type=int,
                        help="override target stress warm-up")
    parser.add_argument("--db", help="override SQLite database path")
    parser.add_argument("--deploy", action="store_true",
                        help="rsync rt-handler to the target before run")
    parser.add_argument("--build", action="store_true",
                        help="build source rt-handler on the target before run")
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
