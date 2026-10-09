# A complete standalone GPIO experiment

[Русский](../ru/usage/standalone-gpio-walkthrough.md)

**Goal:** measure a VisionFive 2 userspace GPIO request/response round trip with
an Arduino Mega 2560, retain a SQLite session, check integrity, and interpret a
graph. Standard execution uses ALT Linux RPM packages. Plotting and firmware
preparation use a source checkout. See the [validation record](../reference/validation.md)
for checks executed during documentation preparation versus pending stand checks.

## 1. Understand the measured path

![Standalone request/response path](../assets/standalone-gpio-path.svg)

GPIO means general-purpose input/output. Latency here is elapsed time between
the Arduino's request transition and its detected response transition. It includes
electrical adaptation, target GPIO/interrupt handling, and `rt-handler` userspace
processing. It is not cyclictest scheduler wake-up latency. PREEMPT_RT is the
Linux real-time preemption configuration, not a guarantee that every path meets
a deadline. The reference runner needs a schedulable threaded GPIO IRQ; verify
that your kernel/handler exposes it before collecting data.

Required roles:

| Role | Required preparation |
|---|---|
| Controlling PC | ALT Linux, `rt-tester-tools`, SSH, USB serial access, free receiver port 9101 |
| VisionFive 2 | ALT Linux, compatible `rt-handler`, SSH, running `node_exporter`, threaded GPIO IRQ |
| Arduino Mega 2560 | This repository's firmware, USB cable, suitable level adaptation |
| Wiring | Request and response paths plus common GND, mapped to the installed handler profile |

Local or central Prometheus/Grafana is a separate optional scenario. Start with
plain collection so a dashboard failure cannot be confused with a wiring failure.

## 2. Install tools and record the environment

On the PC, with the project package available from a configured repository:

```bash
apt-get install rt-tester-tools
rt-tester-run-gpio --help
```

Use the [installation reference](../reference/dependencies.md) when installing a
supplied local RPM. Run package installation with appropriate administrative
privileges; run PC collection as the user owning the experiment files and serial
device access.

On the target:

```bash
apt-get install rt-handler prometheus-node_exporter openssh-server
command -v rt-handler node_exporter chrt taskset
uname -r
rpm -q rt-handler prometheus-node_exporter
```

Configure/start SSH and `node_exporter` using the installed package's service
units. Check the actual unit name on your installation; the binary is
`node_exporter`, while the package is `prometheus-node_exporter`.
The current runner requires and pins a **running** `node_exporter` even when
Prometheus/Grafana startup is disabled.

From the PC, replace the example host with yours and establish SSH host-key trust:

```bash
export TARGET_HOST=192.0.2.10
ssh "root@$TARGET_HOST" 'uname -r; pgrep -a -x node_exporter; cat /proc/interrupts'
ssh -o BatchMode=yes "root@$TARGET_HOST" 'command -v rt-handler node_exporter chrt taskset'
export TARGET_KERNEL=$(ssh -o BatchMode=yes "root@$TARGET_HOST" uname -r)
```

`192.0.2.10` is a documentation address: replace it with the reachable target.
Root SSH is used here because the runner changes scheduling/affinity and target
processes. An alternative account must have equivalent configured permissions.
Record board revision, kernel package/configuration, CPU frequency governor,
handler package, CPU/IRQ placement, and workload alongside results.

Obtain the source needed for firmware and later plotting:

```bash
mkdir -p "$HOME/src"
git clone https://altlinux.space/besogon1238/rt-tester.git "$HOME/src/rt-tester"
export RT_TESTER_SOURCE="$HOME/src/rt-tester"
git -C "$RT_TESTER_SOURCE" rev-parse HEAD
```

If you already have a checkout, set `RT_TESTER_SOURCE` to its absolute path and
record its revision. Use a checkout matching the documentation/tool revision;
an older RPM may not yet contain the new example profiles. In that case copy
profiles from the matching checkout, not an unrelated development revision.

## 3. Prepare firmware, wiring, and serial

Build/upload `src/arduino-meter/arduino-meter.ino` for Mega 2560 using Arduino IDE
or your configured Arduino CLI, Arduino AVR core, and ArduinoJson. Record the
source revision and actual tool/library versions. This step is not automated by
the PC tools RPM; see [Arduino preparation](../hardware/arduino.md).

| Signal | Connection |
|---|---|
| Request | Arduino D7 → 5 V to 3.3 V adaptation → target request GPIO |
| Response | Target response GPIO → suitable return adaptation → Arduino D20 |
| Reference | Common GND between Arduino, adapter, and target |

The historical `starfive` handler mapping is `/dev/gpiochip0` offsets 60 and 61.
Confirm the **installed** `/etc/rt-handler/boards.d/` profile and built-in mapping
against your board revision and kernel's GPIO enumeration. Those offsets are
not physical header pins. Record the corresponding header positions using the
board pinout before wiring; do not infer them from Linux line numbers.
The [target GPIO reference](../hardware/target-gpio.md) separates these namespaces.

Mega uses 5 V logic, while target GPIO is 3.3 V. D20 is configured as
`INPUT_PULLUP`; the return adapter must account for its pull-up and input threshold.
Keep request/response independent: a direct loopback can produce plausible
small numbers without measuring the handler. Confirm wiring/levels with the
board and adapter documentation before power-on.

Discover PC serial ports:

```bash
python3 -m serial.tools.list_ports -v
```

Give the collecting user access through the device's group/udev policy, reconnect
or re-login as required, and close Arduino IDE's serial monitor before a run.
Set `arduino-port` in the copied profile when automatic discovery is ambiguous.
The runner/receiver reference uses 115200 baud; changing `arduino-baud` alone
does not change receiver baud. Use matching firmware at 115200 for this example.

## 4. Create a reader-owned experiment directory and profiles

```bash
mkdir -p "$HOME/rt-experiments/visionfive2-gpio"
cd "$HOME/rt-experiments/visionfive2-gpio"
mkdir -p .rt-tester-example
cp /usr/share/rt-tester-tools/configs/stands/examples/visionfive2-gpio-*.conf .
```

When using matching source profiles instead, replace the last command with:

```bash
cp "$RT_TESTER_SOURCE"/configs/stands/examples/visionfive2-gpio-*.conf .
```

The following preparation applies your target/kernel and turns all example PC
paths into absolute paths. Run it once on fresh copies from this directory:

```bash
python3 - <<'PY'
import os
from pathlib import Path
state = str((Path.cwd() / '.rt-tester-example').resolve())
for profile in Path.cwd().glob('visionfive2-gpio-*.conf'):
    text = profile.read_text()
    text = text.replace('TARGET_HOST', os.environ['TARGET_HOST'])
    text = text.replace('TARGET_KERNEL', os.environ['TARGET_KERNEL'])
    text = text.replace('.rt-tester-example', state)
    profile.write_text(text)
PY
```

Inspect the copies before running. The target `board = starfive` selects the
handler's VisionFive 2 mapping; the user-facing label is `visionfive2`.
Confirm `irq-name`, CPUs, priorities, serial selection, kernel, and paths.
The example assumes CPU 1 for handler/IRQ and CPUs 0,3 for housekeeping.
Changing these choices changes the experiment. Central transport is adapted
separately in [central observability](../observability/central.md).

For installed `0.4.2`, absolute paths are important: the runner launches receiver from its own source
directory, so a relative database path is **not** reliably relative to your
experiment directory. INI files do not perform general shell interpolation;
do not write literal `$PWD` or `$HOME` in runner paths.

Reference parameters are 1500 requests/group, 1000 µs minimum interval,
10000 µs response deadline, and 100 groups, stress off. No-loss groups retain
75 worst response samples. A nominal full run is 150 seconds plus preparation,
serial/processing overhead, and any response waits. Smoke is not characterization.

## 5. Run and check a three-group smoke

```bash
SMOKE_ID=$(date +%s)
rt-tester-run-gpio --config ./visionfive2-gpio-basic.conf \
  --session-id "$SMOKE_ID" --groups 3 \
  --db "$PWD/.rt-tester-example/smoke.db" \
  --no-prometheus --no-grafana
```

Both disabling flags are required for the basic profile. The runner still
starts the receiver metrics endpoint and requires target `node_exporter`.
Use the stand exclusively: the current runner cleans up old handlers, local
receivers, and target stress processes; it owns target lifecycle during the run.

Expected output includes `Stand`, `Session ID`, `Execution mode: userspace`,
`Arduino serial preflight OK`, group progress, `SQLite summary`, and
`GPIO measurement completed successfully`. This is an output checklist, not
a transcript of a newly executed hardware run.

For a no-loss smoke, summary should identify groups `(3, 0, 2)`, 225 stored
latencies, and integrity `(4500, 4500, 4500, 0, 0)`: expected requests, sent
requests, responses, timeouts, bad groups. Latency values depend on your stand.
Exit status 2 indicates the runner's anomaly summary; inspect the preserved DB
and target log rather than interpreting it as a successful clean experiment.

`--dry-run` writes generated configuration files and can probe HTTP state;
it is not a read-only preflight. `--prepare-only` also changes target state.

## 6. Collect the reference session

```bash
export SESSION_ID=$(date +%s)
rt-tester-run-gpio --config ./visionfive2-gpio-basic.conf \
  --session-id "$SESSION_ID" --groups 100 \
  --db "$PWD/.rt-tester-example/gpio.db" \
  --no-prometheus --no-grafana
```

Use a fresh session ID for every run. Save it with the edited profile, firmware
revision, versions, wiring/levels, frequency policy, and measured conditions.
The no-loss target is 100 groups, 150000 requests/responses, zero timeouts, and
7500 retained latency rows. Nominal group duration is not guaranteed wall-clock
duration. The runner stops the target handler after collection; managed monitoring
in the later scenarios persists until explicitly stopped.

## 7. Verify integrity in the primary artifact

With receiver stopped, run from the experiment directory:

```bash
python3 - <<'PY'
import os, sqlite3
from pathlib import Path
sid = int(os.environ['SESSION_ID'])
uri = (Path('.rt-tester-example/gpio.db').resolve().as_uri() + '?mode=ro')
with sqlite3.connect(uri, uri=True) as conn:
    print('SQLite:', conn.execute('PRAGMA integrity_check').fetchone()[0])
    groups = conn.execute('SELECT count(*), min(group_index), max(group_index), '
        'count(DISTINCT group_index) FROM groups WHERE session_id=?', (sid,)).fetchone()
    counts = conn.execute('SELECT sum(requests_sent), sum(responses_received), '
        'sum(timeout_count) FROM groups WHERE session_id=?', (sid,)).fetchone()
    bad = conn.execute('SELECT count(*) FROM groups WHERE session_id=? AND '
        '(requests_sent != measurements_per_group OR responses_received != requests_sent '
        'OR timeout_count != 0)', (sid,)).fetchone()[0]
    tail = conn.execute('SELECT count(*) FROM latencies l JOIN groups g '
        'ON g.id=l.group_id WHERE g.session_id=?', (sid,)).fetchone()[0]
    events = conn.execute('SELECT event_type,count(*) FROM events WHERE session_id=? '
        'GROUP BY event_type', (sid,)).fetchall()
    print('groups / counters / tail / events:', groups, counts, tail, events)
    assert groups == (100, 0, 99, 100)
    assert counts == (150000, 150000, 0) and bad == 0
    assert tail == 7500
    assert not any(kind in ('fall', 'recovery') for kind, count in events)
print('Reference no-loss checks passed')
PY
```

Inspect any additional events and preserved diagnostics. This SQL check complements
the runner summary: the plotting validator currently does not check response
counters, and its printed failures are not a reliable nonzero process exit.
No imported trace rows are expected for standalone; no SoC rows are expected
when there is no reachable Prometheus.

For an archive, close collector processes and use SQLite's backup mechanism
to produce a consistent snapshot; copying just `.db` while a writer has pending
WAL data may omit committed results. Keep the original and its experiment notes.

## 8. Plot the stored tail

On the PC, install available ALT plotting packages:

```bash
apt-get install python3-module-pandas python3-module-numpy python3-module-matplotlib
python3 "$RT_TESTER_SOURCE/src/pc-receiver/plot_statistics.py" \
  "$PWD/.rt-tester-example/gpio.db" --session "$SESSION_ID" \
  --top 75 --limit 250 --output "$PWD/.rt-tester-example/latency.png" latency
```

These are source-only tools. The line called “Average Latency” is the mean of
the selected retained tail **per group**, not the mean of all 1500 responses.
The shaded range extends to that group's observed maximum. The threshold is an
analysis choice, not the response deadline; 250 µs is illustrative here.
See [statistics](../reference/measurement-statistics.md) before making comparisons.

## 9. Read a real historical result

![Historical retained-tail means, session 186819](../assets/visionfive2-session-186819.svg)

This packaged SVG was derived from the tracked database
`tests/old_databases/28032026.db`, session `186819`. Historical setup and the
original plot are recorded in `tests/visionfive_tests.md` and
`tests/results_starfive/186819_visionfive_6.18_300_75_stress_off.png` in the checkout.
It was a direct VisionFive 2 userspace GPIO experiment, not a supervised run.

| Stored property | Historical value |
|---|---:|
| Kernel / workload labels | `6.18` / stress off |
| Groups / requests per group | 2500 / 1500 |
| Minimum request interval | 300 µs |
| Retained values per group / total | 75 / 187500 |
| Pooled retained-tail mean | 164.679701 µs |
| Observed maximum stored latency | 348 µs |
| Average recorded whole-group jitter | 25.769485 µs |
| SoC metric rows | 2337; coverage is incomplete |

Each SVG point averages 7500 tail samples from 100 consecutive groups. The dashed
line is the pooled tail mean. The x-axis is group bins, not wall-clock time;
the y-axis is zoomed. Binning smooths individual outliers—the maximum is reported
separately. The full dataset is available in the checkout, not inside the RPM.

Reproduce the historical latency plot on an **analysis copy**, from your saved
experiment directory:

```bash
python3 - <<'PY'
import os, sqlite3
from pathlib import Path
source = Path(os.environ['RT_TESTER_SOURCE']) / 'tests/old_databases/28032026.db'
destination = Path('.rt-tester-example/historical-analysis.db')
assert not destination.exists(), 'Choose a fresh analysis-copy filename'
with sqlite3.connect(source.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as src:
    with sqlite3.connect(destination) as dst:
        src.backup(dst)
        dst.execute("ALTER TABLE groups ADD COLUMN target_payload TEXT DEFAULT 'unknown'")
PY
python3 "$RT_TESTER_SOURCE/src/pc-receiver/plot_statistics.py" \
  "$PWD/.rt-tester-example/historical-analysis.db" --session 186819 \
  --top 75 --limit 250 --output "$PWD/.rt-tester-example/historical-latency.png" latency
```

The added `target_payload` field is only compatibility metadata required by the
current plotter and is explicitly unknown; the original DB remains unchanged.
Do not run the current generic validator/report on this legacy schema as if it
had current counters/trace tables. `immutable=1` is appropriate here only because
the versioned historical source is a closed snapshot, not a live experiment DB.

**Supported interpretation:** the stored worst 5% averaged about 164.68 µs and
the observed stored maximum was 348 µs for that historical run.
**Unsupported interpretation:** every request met a deadline, overall response
p99 was 164.68 µs, or PREEMPT_RT caused an improvement. This legacy DB has no
response/timeout counters and lacks exact kernel, handler, firmware, affinity,
and governor versions. Its 300 µs interval differs from the new 1000 µs example.

## 10. Add observability or design the next experiment

Continue with [local Prometheus/Grafana](../observability/local.md), then
[central metric delivery](../observability/central.md) when required. Retain
SQLite independently of live dashboards. For longer series, idle/stress or
kernel comparisons, use [GPIO methodology](../methodology/gpio-measurements.md)
and record all controlled conditions; a smoke maximum is not a worst-case bound.

| Symptom | First check |
|---|---|
| Arduino not detected / cannot open | USB device, permissions, chosen port, another serial application |
| Missing IRQ thread / pinning failure | Installed handler mapping, kernel IRQ threading, `irq-name` and CPUs |
| Timeouts or implausibly tiny latency | Wiring, adapter, shared GND, actual handler response versus loopback |
| DB not where expected | Absolute `--db`/profile path and receiver working directory |
| Empty dashboard | Verify receiver, local scrape, datasource/session/time range before changing measurement |
