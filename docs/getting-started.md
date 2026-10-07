# Getting started

[Русский](ru/getting-started.md)

## 1. Choose the measured path

| Mode | Measurement | Arduino | Installed command |
|---|---|---:|---|
| Standalone GPIO | GPIO request/handler/response round trip | Yes | `rt-tester-run-gpio` |
| Supervised raw Ethernet | Controller, transport, supervisor, runtime round trip | Yes | `rt-tester-run-stand` |
| Linux benchmark | Scheduler wake-up latency | No | `rt-tester-run-linux-benchmark` |

GPIO means general-purpose input/output. The Arduino measures elapsed time
between a request transition and a response transition. PREEMPT_RT is a Linux
real-time preemption configuration; it does not make every measured path or
observed maximum a guaranteed deadline.

## 2. Prepare the roles

The controlling PC runs the tools and stores primary artifacts. Targets need
SSH access, permissions to change scheduling/affinity, and mode-specific
software. GPIO modes also need flashed Arduino firmware, correct wiring, level
adaptation, and a common ground. A central server is optional.

On ALT Linux, when your configured repository provides the package:

```bash
apt-get install rt-tester-tools
```

See [dependencies](reference/dependencies.md) for local RPM installation,
target packages, and plotting dependencies. The standalone runner requires a
running target `node_exporter` even with observability disabled.

## 3. Own your configuration

Follow the [standalone walkthrough](usage/standalone-gpio-walkthrough.md) for a
complete setup. Copy one of these installed examples into your saved experiment
directory and edit the copy:

```text
/usr/share/rt-tester-tools/configs/stands/examples/visionfive2-gpio-basic.conf
/usr/share/rt-tester-tools/configs/stands/examples/visionfive2-gpio-local.conf
/usr/share/rt-tester-tools/configs/stands/examples/visionfive2-gpio-central.conf
```

Replace `root@TARGET_HOST`, check board/kernel labels and GPIO configuration,
Arduino serial access, group size, interval, response timeout, workload, and
output paths. Central mode also needs your server/account/key. Neutral examples
use PC ports `9101` (receiver), `9092` (Prometheus), and `3002` (Grafana or central
Grafana forward). Convert the example `.rt-tester-example` paths to absolute paths
using the walkthrough's preparation step: receiver runs in a different working
directory, and an unadapted relative database path can resolve there instead.

## 4. Check a short run before collecting a series

After completing the hardware and target preparation:

```bash
rt-tester-run-gpio --config ./visionfive2-gpio-basic.conf \
  --groups 3 --no-prometheus --no-grafana
```

Basic requires both disabling flags. Local/central profiles are separate
scenarios, described in [local](observability/local.md) and
[central observability](observability/central.md). Use several groups for live
dashboard checks; a single group can finish before a scrape captures it.

Other prepared stands use:

```bash
rt-tester-run-stand --config ./supervised.conf \
  --groups 3 --no-prometheus --no-grafana
rt-tester-run-linux-benchmark --config ./cyclictest.conf --duration 10
```

GPIO runners' `--dry-run` is not a read-only validation mode: it can write
generated configs and probe local state. For inspecting CLI syntax, use `--help`.
`--prepare-only` changes target state and is not a substitute for validation.

## 5. Preserve and validate

Check group continuity, request/response/timeout accounting, events, and labels
before increasing the number of groups. GPIO data is in the configured SQLite
database; cyclictest prints a finalized bundle path. Preserve configs, logs,
versions, and wiring notes with the primary artifact. Continue with
[analysis](usage/analysis-and-reports.md) and the appropriate
[GPIO](methodology/gpio-measurements.md) or
[cyclictest](methodology/cyclictest-comparisons.md) methodology.

For source builds or extensions, use the secondary
[developer route](development/development-and-testing.md).
