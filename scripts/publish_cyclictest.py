#!/usr/bin/env python3
"""Publish validated cyclictest bundles to a remote rt-results catalog."""

from __future__ import annotations

import argparse
import configparser
import datetime as dt
import hashlib
import json
import shlex
import subprocess
import sys
import uuid
from pathlib import Path


SECTION = "publish"


def q(value: object) -> str:
    return shlex.quote(str(value))


def value(
    cfg: configparser.ConfigParser, key: str, default: str = ""
) -> str:
    if cfg.has_option(SECTION, key):
        return cfg.get(SECTION, key).strip()
    return default


def required(cfg: configparser.ConfigParser, key: str) -> str:
    result = value(cfg, key)
    if not result:
        raise ValueError(f"missing [{SECTION}] {key}")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_bundle(bundle: Path) -> dict:
    bundle = bundle.expanduser().resolve()
    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported bundle schema version")
    if manifest.get("benchmark_type") != "cyclictest":
        raise ValueError("bundle is not a cyclictest benchmark")
    if manifest.get("completion_status") != "complete":
        raise ValueError("bundle is not complete")
    run_uid = str(uuid.UUID(manifest["run_uid"]))
    if run_uid != manifest["run_uid"]:
        raise ValueError("run_uid is not canonical")
    declared = {artifact["path"] for artifact in manifest.get("artifacts", [])}
    required_artifacts = {"cyclictest.json", "histogram.txt"}
    if not required_artifacts.issubset(declared):
        raise ValueError("manifest does not declare required cyclictest artifacts")
    actual = {
        str(path.relative_to(bundle))
        for path in bundle.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if actual != declared:
        raise ValueError("bundle files do not match the artifact manifest")
    for artifact in manifest["artifacts"]:
        path = (bundle / artifact["path"]).resolve()
        if not path.is_relative_to(bundle):
            raise ValueError(f"artifact escapes bundle: {artifact['path']}")
        if not path.is_file():
            raise ValueError(f"missing artifact: {artifact['path']}")
        if path.stat().st_size != int(artifact["size"]):
            raise ValueError(f"artifact size mismatch: {artifact['path']}")
        if sha256(path) != artifact["sha256"]:
            raise ValueError(f"artifact digest mismatch: {artifact['path']}")
    return manifest


def _state_path(cfg: configparser.ConfigParser, run_uid: str) -> Path:
    root = Path(value(
        cfg,
        "state-directory",
        "~/.local/state/rt-tester/cyclictest-publish",
    )).expanduser()
    return root / f"{run_uid}.json"


def _write_state(
    cfg: configparser.ConfigParser,
    manifest: dict,
    bundle: Path,
    status: str,
    *,
    error: str = "",
) -> None:
    path = _state_path(cfg, manifest["run_uid"])
    attempts = 0
    if path.is_file():
        try:
            attempts = int(json.loads(path.read_text(encoding="utf-8"))["attempts"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            attempts = 0
    payload = {
        "schema_version": 1,
        "run_uid": manifest["run_uid"],
        "bundle": str(bundle),
        "status": status,
        "attempts": attempts + (1 if status == "publishing" else 0),
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if error:
        payload["error"] = error
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _run(
    command: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(q(part) for part in command))
    sys.stdout.flush()
    return subprocess.run(command, check=check, text=True)


def _ssh_options(cfg: configparser.ConfigParser) -> list[str]:
    options = ["-p", value(cfg, "port", "22"), "-o", "BatchMode=yes"]
    identity = value(cfg, "identity")
    if identity:
        options.extend(["-i", str(Path(identity).expanduser())])
    return options


def publish_bundle(
    bundle: Path,
    cfg: configparser.ConfigParser,
    *,
    execute=_run,
) -> None:
    bundle = bundle.expanduser().resolve()
    manifest = validate_bundle(bundle)
    run_uid = manifest["run_uid"]
    host = required(cfg, "host")
    remote_root = value(
        cfg, "remote-directory", "/tmp/rt-tester-cyclictest-publish"
    ).rstrip("/")
    remote_bundle = f"{remote_root}/{run_uid}.partial"
    importer = value(cfg, "importer", "/usr/bin/rt-results-import-cyclictest")
    database = value(
        cfg,
        "database",
        "/var/lib/rt-results-prototype/cyclictest.db",
    )
    ssh_options = _ssh_options(cfg)
    ssh = ["ssh", *ssh_options, host]
    scp_options = ["-P", value(cfg, "port", "22"), "-o", "BatchMode=yes"]
    identity = value(cfg, "identity")
    if identity:
        scp_options.extend(["-i", str(Path(identity).expanduser())])

    _write_state(cfg, manifest, bundle, "publishing")
    try:
        execute([
            *ssh,
            f"rm -rf {q(remote_bundle)} && install -d -m700 {q(remote_bundle)}",
        ])
        execute([
            "scp", *scp_options, "-r", f"{bundle}/.",
            f"{host}:{remote_bundle}/",
        ])
        execute([
            *ssh,
            f"{q(importer)} {q(remote_bundle)} --output {q(database)}",
        ])
        verify_code = (
            "import sqlite3,sys; "
            "db=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); "
            "raise SystemExit(0 if db.execute("
            "'SELECT 1 FROM runs WHERE run_uid=?',(sys.argv[2],)"
            ").fetchone() else 1)"
        )
        execute([
            *ssh,
            f"python3 -c {q(verify_code)} {q(database)} {q(run_uid)}",
        ])
    except Exception as error:
        _write_state(cfg, manifest, bundle, "pending", error=str(error))
        raise
    else:
        _write_state(cfg, manifest, bundle, "published")
        print(f"Published bundle: {run_uid}")
    finally:
        try:
            execute([*ssh, f"rm -rf {q(remote_bundle)}"], check=False)
        except OSError as error:
            print(f"warning: remote staging cleanup failed: {error}", file=sys.stderr)


def load_config(path: Path) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(interpolation=None)
    with path.expanduser().open("r", encoding="utf-8") as source:
        cfg.read_file(source)
    return cfg


def pending_bundles(cfg: configparser.ConfigParser) -> list[Path]:
    state_root = _state_path(cfg, "placeholder").parent
    bundles = []
    for path in sorted(state_root.glob("*.json")):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(
                f"warning: cannot read publication state {path}: {error}",
                file=sys.stderr,
            )
            continue
        if state.get("status") != "published":
            bundle = Path(state["bundle"])
            if bundle.is_dir():
                bundles.append(bundle)
    return bundles


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", nargs="*", type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--pending", action="store_true")
    args = parser.parse_args()
    cfg = load_config(args.config)
    bundles = list(args.bundle)
    if args.pending:
        bundles.extend(pending_bundles(cfg))
    if not bundles:
        parser.error("provide a bundle or --pending")
    failed = False
    for bundle in dict.fromkeys(bundles):
        try:
            publish_bundle(bundle, cfg)
        except Exception as error:
            failed = True
            print(f"publication failed for {bundle}: {error}", file=sys.stderr)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
