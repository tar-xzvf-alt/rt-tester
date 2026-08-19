#!/usr/bin/env python3
"""Central Prometheus/Grafana transport for measurement runners."""

from __future__ import annotations

import configparser
import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


SECTION = "observability"


def value(cfg: configparser.ConfigParser, key: str, default: str = "") -> str:
    if cfg.has_option(SECTION, key):
        return cfg.get(SECTION, key).strip()
    return default


def enabled(cfg: configparser.ConfigParser) -> bool:
    return bool(value(cfg, "remote-write-url"))


def external_labels(cfg: configparser.ConfigParser, monitor: str) -> str:
    collector = value(cfg, "collector-label", os.uname().nodename)
    stand = cfg.get("stand", "name").strip()
    return "\n".join([
        f"    monitor: {json.dumps(monitor)}",
        f"    collector: {json.dumps(collector)}",
        f"    stand: {json.dumps(stand)}",
    ])


def remote_write_block(cfg: configparser.ConfigParser) -> str:
    url = value(cfg, "remote-write-url")
    if not url:
        return ""
    return "\n".join([
        "",
        "remote_write:",
        f"  - url: {json.dumps(url)}",
        "    remote_timeout: 30s",
        "    queue_config:",
        "      capacity: 10000",
        "      max_shards: 4",
        "      min_shards: 1",
        "      max_samples_per_send: 1000",
        "      batch_send_deadline: 1s",
    ])


def managed_grafana(cfg: configparser.ConfigParser) -> bool:
    return value(cfg, "grafana-managed", "true").lower() in (
        "1", "on", "true", "yes"
    )


def grafana_url(cfg: configparser.ConfigParser) -> str:
    return value(cfg, "grafana-url")


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.URLError):
        return False


def _pid_path(cfg: configparser.ConfigParser) -> Path:
    raw = value(
        cfg, "central-tunnel-pid",
        "~/.local/state/rt-tester/central-observability-tunnel.pid",
    )
    return Path(raw).expanduser()


def stop_tunnel(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    pid_path = _pid_path(cfg)
    if not pid_path.exists():
        return
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except ValueError:
        pid_path.unlink(missing_ok=True)
        return
    if dry_run:
        print(f"would stop central observability tunnel pid {pid}")
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    pid_path.unlink(missing_ok=True)


def start_tunnel(cfg: configparser.ConfigParser, *, dry_run: bool) -> None:
    if not enabled(cfg):
        return
    host = value(cfg, "central-ssh-host")
    if not host:
        raise ValueError(
            "[observability] central-ssh-host is required with remote-write-url"
        )
    ssh_port = value(cfg, "central-ssh-port", "22")
    identity = value(cfg, "central-ssh-identity")
    prometheus_port = value(cfg, "central-prometheus-local-port", "19090")
    grafana_port = value(cfg, "central-grafana-local-port", "13000")
    ready_url = f"http://127.0.0.1:{prometheus_port}/-/ready"
    if _http_ok(ready_url):
        print(f"Central observability tunnel already healthy: {ready_url}")
        return

    stop_tunnel(cfg, dry_run=dry_run)
    pid_path = _pid_path(cfg)
    log_path = Path(value(
        cfg, "central-tunnel-log",
        "~/.local/state/rt-tester/central-observability-tunnel.log",
    )).expanduser()
    cmd = ["ssh", "-N", "-T", "-p", ssh_port]
    if identity:
        cmd.extend(["-i", str(Path(identity).expanduser())])
    cmd.extend([
        "-o", "BatchMode=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-L", f"127.0.0.1:{prometheus_port}:127.0.0.1:9090",
        "-L", f"127.0.0.1:{grafana_port}:127.0.0.1:3000",
        host,
    ])
    print("$ " + " ".join(cmd))
    if dry_run:
        return

    pid_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("ab")
    proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
    pid_path.write_text(f"{proc.pid}\n", encoding="utf-8")
    for _ in range(30):
        if proc.poll() is not None:
            raise OSError(
                f"central observability tunnel exited; see {log_path}"
            )
        if _http_ok(ready_url):
            print(f"Central observability tunnel ready: {ready_url}")
            return
        time.sleep(0.2)
    proc.terminate()
    pid_path.unlink(missing_ok=True)
    raise OSError(f"central Prometheus is not ready; see {log_path}")
