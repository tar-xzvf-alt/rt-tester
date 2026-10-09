# Development and testing

[Русский](../ru/development/development-and-testing.md)

Read the [architecture](architecture.md) before changing a measurement path.
Commands below run from the repository root in a source checkout, unless stated
otherwise. The installed RPM is the normal experiment path; offline plotting and
merging require source. See [dependencies](../reference/dependencies.md).

## Source dependencies

The Python tools do not need a compilation step. On ALT Linux, collector imports
are supplied by:

```bash
apt-get install python3 python3-module-serial python3-module-requests
```

Plotting additionally imports `pandas`, `numpy`, `matplotlib` (ALT packages
`python3-module-pandas`, `python3-module-numpy`, `python3-module-matplotlib`).
The installed runners use standard-library modules plus external commands such
as SSH/SCP and rsync; real runs require the role-specific target dependencies.
`metrics_server.py` implements HTTP exposition with the standard library: the
third-party `prometheus-client` package is not required. The local file
`prometheus_client.py` uses `requests`, and must not be confused with that package.
Only the historical `soc_monitor.py` needs `paramiko`.

Alternatively, in an environment with Python venv/pip support, create a disposable
environment outside tracked artifacts:

```bash
python3 -m venv "$HOME/.venvs/rt-tester"
. "$HOME/.venvs/rt-tester/bin/activate"
python3 -m pip install pyserial requests pandas numpy matplotlib
```

The import `serial` comes from **pyserial**, not the unrelated package named
`serial`. Install `paramiko` only when working on the historical SSH helper.
Firmware builds need the Arduino Mega 2560 core, AVR toolchain and ArduinoJson;
target responder/supervisor builds belong to their external repositories, not
this PC source setup. No firmware compilation or upload is covered by unittest.

## Automated checks without a stand

Run the repository's check command:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
```

Focused examples use discovery because `tests/` is not a Python package:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_receiver_integrity.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_run_stand_measurement.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_run_linux_benchmark.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_publish_cyclictest.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_documentation.py'
```

| Tests | What they check |
|---|---|
| `test_run_gpio_measurement.py` | Backend/tuning/cleanup command generation and paired-profile parameters |
| `test_receiver_integrity.py` | Temporary SQLite storage and complete/timeout group validation |
| `test_run_stand_measurement.py` | Mocked startup gate/progress, lifecycle commands, network policy and trace-import failure handling |
| `test_central_observability.py` | Generated identity/configuration, tunnel commands and remote Grafana selection |
| `test_run_linux_benchmark.py` | Command generation, result validation, scoped stress lifecycle and metadata |
| `test_publish_cyclictest.py` | Mocked remote import, retry state and artifact tampering rejection |
| `test_documentation.py` | Document structure, local links/assets, language switches, executable example parity and JSON semantics |
| `test_documentation_profiles.py` | Adapted reference profiles through receiver/Prometheus/Grafana generators; basic flags skip monitoring startup |
| `test_gpio_config_failures.py` | Kernel diagnostics, stdout/stderr isolation, bounded SSH, edited exporter hosts and DB path consistency |
| `test_runner_cleanup.py` | Startup/diagnostic/cleanup failures, preserved interrupts, scoped stops, finalized bundle retention and real local child-process cleanup |

Tests mock subprocess/network boundaries or use temporary data. They do not prove
GPIO wiring, timing, firmware serial interoperability, kernel-module compatibility,
SSH access, remote-write delivery or dashboard correctness. Link checks do not
check external URLs or Markdown anchors. Record executed and pending verification
in [validation](../reference/validation.md).

Safe CLI parsing checks exit before collector construction or runner execution:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 src/pc-receiver/receiver.py --help
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_gpio_measurement.py --help
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_stand_measurement.py --help
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_linux_benchmark.py --help
PYTHONDONTWRITEBYTECODE=1 python3 scripts/publish_cyclictest.py --help
```

Do not use full GPIO/supervised runners as an offline smoke check, including
`--dry-run`: they can prepare directories, receiver configuration and observability
files. Prefer isolated config parsing, command generation and validation functions
with mocked external calls, following existing tests. Merely constructing
`ArduinoCollector` creates a database and starts an HTTP server.

## Static historical data and test isolation

For static, checkpointed tracked databases, inspect with an immutable read-only
URI to avoid creating WAL/SHM sidecars or changing journal settings:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import sqlite3
from pathlib import Path
path = Path('tests/old_databases/28032026.db').resolve()
with sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True) as conn:
    print(conn.execute('PRAGMA integrity_check').fetchone()[0])
    print(conn.execute('SELECT COUNT(*) FROM groups').fetchone()[0])
PY
```

`immutable=1` assumes the database cannot change and ignores journal recovery;
do not use it for an active collection database or data with uncheckpointed WAL.
For plotting/merging checks, use a disposable copy of a finalized database and
place outputs in a reader-owned temporary directory. Current tools use ordinary
SQLite connections; `database.py` explicitly enables WAL even for its reads.
Never initialize a tracked historical fixture through that module. See
[analysis](../usage/analysis-and-reports.md) and
[statistics](../reference/measurement-statistics.md) for interpretation limits.

Database-writing tests use `TemporaryDirectory` and reset `database._db_manager`
before and after each case because its cached manager keeps the first path.
Follow that isolation pattern for current tests; changing only the path argument
does not select another database in the same process. Patch subprocess, SSH and
HTTP at the called boundary, and check meaningful results such as rejected
timeouts or a start gate released only after readiness.

## Packaging boundary

`.gear/rt-tester-tools.spec` defines installed wrappers, source assets, `%doc` and
the `%check` suite. Source verification does not establish installed RPM contents
or packaged links. After documentation approval, prepare the release source
snapshot, update version/release and changelog, and build with explicit hasher
target/APT/workdir settings. Record package checks and installed-content inspection
separately from source tests. `BuildArch: noarch` produces an architecture-neutral
RPM; rebuilding in other target environments checks dependencies and `%check`.

Next: [change guide](change-guide.md).
