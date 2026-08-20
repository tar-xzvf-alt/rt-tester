#!/usr/bin/env python3
"""Run a Linux responsiveness benchmark on a remote target."""

from __future__ import annotations

import argparse
import configparser
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from publish_cyclictest import publish_bundle


BUNDLE_SCHEMA_VERSION = 1
CYCLICTEST_JSON_VERSION = 1


def q(value: object) -> str:
    return shlex.quote(str(value))


def die(message: str) -> None:
    raise SystemExit(f"error: {message}")


def load_config(path: Path) -> configparser.ConfigParser:
    if not path.is_file():
        die(f"config not found: {path}")
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.optionxform = str.lower
    with path.open("r", encoding="utf-8") as source:
        cfg.read_file(source)
    return cfg


def require(cfg: configparser.ConfigParser, section: str, key: str) -> str:
    if not cfg.has_option(section, key):
        die(f"missing [{section}] {key}")
    value = cfg.get(section, key).strip()
    if not value:
        die(f"empty [{section}] {key}")
    return value


def optional(
    cfg: configparser.ConfigParser, section: str, key: str, default: str
) -> str:
    if cfg.has_option(section, key):
        return cfg.get(section, key).strip()
    return default


def config_bool(value: str) -> bool:
    return value.lower() in ("1", "on", "true", "yes")


def run(
    cmd: list[str], *, check: bool = True, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(q(part) for part in cmd))
    sys.stdout.flush()
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def ssh(
    host: str, command: str, *, check: bool = True, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    return run(
        ["ssh", "-o", "BatchMode=yes", host, command],
        check=check,
        capture=capture,
    )


def remote_value(host: str, command: str) -> str:
    return ssh(host, command, capture=True).stdout.strip()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_duration(value: str) -> str:
    if not re.fullmatch(r"[1-9][0-9]*[mhd]?", value):
        die(f"invalid cyclictest duration: {value}")
    return value


def cyclictest_command(
    cfg: configparser.ConfigParser, remote_dir: str
) -> list[str]:
    if require(cfg, "benchmark", "engine") != "cyclictest":
        die("prototype supports only [benchmark] engine = cyclictest")

    command = [optional(cfg, "benchmark", "binary", "/usr/bin/cyclictest")]
    if config_bool(optional(cfg, "benchmark", "default-system", "true")):
        command.append("--default-system")
    command.extend([
        "--smp",
        f"--policy={optional(cfg, 'benchmark', 'policy', 'fifo')}",
        f"--priority={int(optional(cfg, 'benchmark', 'priority', '95'))}",
        f"--interval={int(optional(cfg, 'benchmark', 'interval-us', '1000'))}",
        f"--distance={int(optional(cfg, 'benchmark', 'distance-us', '0'))}",
        f"--duration={parse_duration(require(cfg, 'benchmark', 'duration'))}",
        f"--histogram={int(optional(cfg, 'benchmark', 'histogram-max-us', '100000'))}",
        f"--histfile={remote_dir}/histogram.txt",
        f"--json={remote_dir}/cyclictest.json",
        "--quiet",
    ])
    if config_bool(optional(cfg, "benchmark", "mlockall", "true")):
        command.append("--mlockall")
    return command


def validate_cyclictest(payload: dict) -> dict:
    if payload.get("file_version") != CYCLICTEST_JSON_VERSION:
        raise ValueError(
            f"unsupported cyclictest JSON version: {payload.get('file_version')}"
        )
    if payload.get("return_code") != 0:
        raise ValueError(f"cyclictest return code: {payload.get('return_code')}")
    threads = payload.get("thread")
    if not isinstance(threads, dict) or not threads:
        raise ValueError("cyclictest JSON has no thread results")
    if payload.get("num_threads") != len(threads):
        raise ValueError("cyclictest thread count does not match num_threads")

    total_cycles = 0
    total_histogram = 0
    for name, result in threads.items():
        if not isinstance(result, dict):
            raise ValueError(f"thread {name} result is not an object")
        cycles = int(result.get("cycles", 0))
        minimum = int(result.get("min", -1))
        maximum = int(result.get("max", -1))
        average = float(result.get("avg", -1))
        if cycles <= 0 or minimum < 0 or maximum < minimum or average < 0:
            raise ValueError(f"thread {name} has invalid summary values")
        histogram = result.get("histogram", {})
        if not isinstance(histogram, dict):
            raise ValueError(f"thread {name} histogram is not an object")
        histogram_count = sum(int(count) for count in histogram.values())
        if histogram_count > cycles:
            raise ValueError(f"thread {name} histogram exceeds cycle count")
        total_cycles += cycles
        total_histogram += histogram_count

    return {
        "threads": len(threads),
        "cycles": total_cycles,
        "histogram_samples": total_histogram,
        "histogram_overflow": total_cycles - total_histogram,
    }


def collect_target_metadata(host: str) -> dict[str, object]:
    governors = remote_value(
        host,
        "for f in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/"
        "scaling_governor; do [ -r \"$f\" ] && "
        "printf '%s=%s\\n' \"$f\" \"$(cat \"$f\")\"; done",
    )
    return {
        "kernel": remote_value(host, "uname -r"),
        "architecture": remote_value(host, "uname -m"),
        "hostname": remote_value(host, "hostname"),
        "cpu_online": remote_value(host, "cat /sys/devices/system/cpu/online"),
        "kernel_cmdline": remote_value(host, "cat /proc/cmdline"),
        "governors": governors.splitlines() if governors else [],
        "cyclictest_package": remote_value(host, "rpm -q linux-rt-tests"),
    }


def preflight(cfg: configparser.ConfigParser) -> dict[str, object]:
    host = require(cfg, "target", "host")
    ssh(host, "true")
    binary = optional(cfg, "benchmark", "binary", "/usr/bin/cyclictest")
    ssh(host, f"test -x {q(binary)}")
    expected_kernel = optional(cfg, "target", "expected-kernel", "")
    metadata = collect_target_metadata(host)
    if expected_kernel and metadata["kernel"] != expected_kernel:
        die(
            f"target kernel {metadata['kernel']} does not match "
            f"{expected_kernel}"
        )
    workload = optional(cfg, "workload", "engine", "idle")
    if workload not in ("idle", "stress-ng"):
        die(f"unsupported [workload] engine: {workload}")
    if workload == "stress-ng":
        ssh(host, "command -v stress-ng >/dev/null")
        metadata["stress_package"] = remote_value(host, "rpm -q stress-ng")
    return metadata


def start_stress(
    cfg: configparser.ConfigParser, remote_dir: str
) -> None:
    if optional(cfg, "workload", "engine", "idle") != "stress-ng":
        return
    host = require(cfg, "target", "host")
    command = require(cfg, "workload", "command")
    ssh(
        host,
        f"setsid sh -c {q('exec ' + command)} "
        f">{q(remote_dir + '/stress.log')} 2>&1 & "
        f"echo $! >{q(remote_dir + '/stress.pid')}",
    )
    warmup = int(optional(cfg, "workload", "warmup-seconds", "60"))
    if warmup > 0:
        ssh(host, f"sleep {warmup}; kill -0 $(cat {q(remote_dir + '/stress.pid')})")


def stop_stress(cfg: configparser.ConfigParser, remote_dir: str) -> None:
    if optional(cfg, "workload", "engine", "idle") != "stress-ng":
        return
    host = require(cfg, "target", "host")
    pid = q(remote_dir + "/stress.pid")
    ssh(
        host,
        f"if [ -s {pid} ]; then p=$(cat {pid}); "
        f"kill -TERM -$p 2>/dev/null || kill -TERM $p 2>/dev/null ||:; "
        f"i=0; while kill -0 $p 2>/dev/null && [ $i -lt 25 ]; do "
        f"sleep .2; i=$((i+1)); done; "
        f"kill -KILL -$p 2>/dev/null ||:; fi",
        check=False,
    )


def artifact_manifest(bundle: Path) -> list[dict[str, object]]:
    artifacts = []
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            artifacts.append({
                "path": str(path.relative_to(bundle)),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            })
    return artifacts


def execute(cfg: configparser.ConfigParser, output_root: Path) -> Path:
    metadata = preflight(cfg)
    host = require(cfg, "target", "host")
    run_uid = str(uuid.uuid4())
    remote_dir = f"/tmp/rt-tester-cyclictest-{run_uid}"
    partial = output_root / f".{run_uid}.partial"
    bundle = output_root / run_uid
    command = cyclictest_command(cfg, remote_dir)
    started_at = utc_now()
    status = "failed"
    exit_code = 1

    partial.mkdir(parents=True)
    try:
        ssh(host, f"rm -rf {q(remote_dir)} && mkdir -m700 {q(remote_dir)}")
        start_stress(cfg, remote_dir)
        result = ssh(
            host,
            " ".join(q(part) for part in command)
            + f" >{q(remote_dir + '/stdout.log')}"
            + f" 2>{q(remote_dir + '/stderr.log')}",
            check=False,
        )
        exit_code = result.returncode
        stop_stress(cfg, remote_dir)
        run(["scp", "-r", f"{host}:{remote_dir}/.", str(partial)])

        result_path = partial / "cyclictest.json"
        if not result_path.is_file():
            raise ValueError("cyclictest did not create JSON output")
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        summary = validate_cyclictest(payload)
        if exit_code != 0:
            raise ValueError(f"cyclictest process exited with {exit_code}")
        status = "complete"

        manifest = {
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "run_uid": run_uid,
            "benchmark_type": "cyclictest",
            "profile": optional(cfg, "benchmark", "profile", "all-cpu"),
            "stand": require(cfg, "stand", "name"),
            "board_model": require(cfg, "target", "label"),
            "workload_type": optional(cfg, "workload", "engine", "idle"),
            "started_at": started_at,
            "completed_at": utc_now(),
            "completion_status": status,
            "exit_code": exit_code,
            "target": metadata,
            "benchmark": {
                "command": command,
                "duration": require(cfg, "benchmark", "duration"),
                "interval_us": int(optional(cfg, "benchmark", "interval-us", "1000")),
                "histogram_max_us": int(optional(cfg, "benchmark", "histogram-max-us", "100000")),
                "policy": optional(cfg, "benchmark", "policy", "fifo"),
                "priority": int(optional(cfg, "benchmark", "priority", "95")),
                "default_system": config_bool(optional(cfg, "benchmark", "default-system", "true")),
                "mlockall": config_bool(optional(cfg, "benchmark", "mlockall", "true")),
            },
            "summary": summary,
        }
        manifest["artifacts"] = artifact_manifest(partial)
        (partial / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        partial.rename(bundle)
        return bundle
    finally:
        stop_stress(cfg, remote_dir)
        ssh(host, f"rm -rf {q(remote_dir)}", check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--duration", help="override cyclictest duration")
    parser.add_argument("--print-command", action="store_true")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="publish the completed bundle to the configured rt-results host",
    )
    args = parser.parse_args()

    cfg = load_config(args.config.expanduser())
    if args.duration:
        if not cfg.has_section("benchmark"):
            cfg.add_section("benchmark")
        cfg.set("benchmark", "duration", parse_duration(args.duration))
    output_root = args.output_root or Path(
        require(cfg, "results", "output-root")
    ).expanduser()

    if args.print_command:
        command = cyclictest_command(cfg, "/tmp/rt-tester-cyclictest-RUN_UID")
        print(" ".join(q(part) for part in command))
        return

    bundle = execute(cfg, output_root)
    print(f"Completed bundle: {bundle}")
    if args.publish:
        try:
            publish_bundle(bundle, cfg)
        except Exception as error:
            print(
                f"warning: measurement complete but publication failed: {error}",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
