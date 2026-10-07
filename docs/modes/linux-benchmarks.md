# Linux responsiveness benchmarks

[Русский](../ru/modes/linux-benchmarks.md)

This mode runs an already installed `cyclictest` on a target over SSH. It measures
scheduler wake-up latency, without Arduino, GPIO, receiver SQLite, or Prometheus
remote write. Use it to compare kernels, workloads, governors, and power policy;
it does not measure the complete physical GPIO response path.

## Preparation

On an ALT target whose repositories provide these packages:

```bash
apt-get install linux-rt-tests openssh-server
# For stressed runs:
apt-get install stress-ng
```

The external `rt-handler-0.1.8-alt1` package also declares benchmark/stress
dependencies; benchmark execution itself does not require using a GPIO handler.
Runner preflight checks SSH, executable cyclictest, expected kernel, package
version, and workload requirements. Failed preflight does not produce a complete
bundle.

Copy and edit the installed laboratory profiles:

```text
/usr/share/rt-tester-tools/configs/stands/visionfive2-rt-cyclictest-idle.conf
/usr/share/rt-tester-tools/configs/stands/visionfive2-rt-cyclictest-stressed.conf
```

Replace private addresses, expected kernel, output root, and publication settings.

```bash
rt-tester-run-linux-benchmark --config ./cyclictest-idle.conf --duration 10m
rt-tester-run-linux-benchmark --config ./cyclictest-stressed.conf --duration 10m
rt-tester-run-linux-benchmark --config ./cyclictest-idle.conf --print-command
rt-tester-run-linux-benchmark --config ./cyclictest-idle.conf \
  --output-root ~/.local/state/rt-tester/my-series
```

`--print-command` prints the generated benchmark command. Use `--help` for CLI
syntax. A ten-second smoke tests the pipeline, not worst-case behavior.

## Parameters and lifecycle

The laboratory VisionFive 2 profiles use one FIFO thread per online CPU:

```text
--default-system --smp --policy=fifo --priority=95
--interval=1000 --distance=0 --mlockall
```

Their stressed workload is:

```text
stress-ng --cpu 4 --cpu-method int64 --vm 1 --vm-bytes 70% --vm-keep --timeout 0
```

The runner records the command and target state, collects native JSON, histogram,
and logs in target `/tmp`, copies them into a local `.<run_uid>.partial`, validates
the artifacts, writes `manifest.json`, and atomically renames the directory to
the finalized `<run_uid>`. It stops the stress process group it created and keeps
its log.

## Primary artifact and publication

A complete bundle includes `manifest.json`, `cyclictest.json`, `histogram.txt`,
`stdout.log`, `stderr.log`, and stressed-run `stress.log`/`stress.pid`. The manifest
records kernel, architecture, governors, tool packages, command, workload, cycles,
histogram overflow, sizes, and SHA256 checksums. Keep finalized bundles unchanged;
publication rejects changed or undeclared files.

Read local metadata/summary in the manifest and per-thread statistics/histogram
in native JSON. [Publishing cyclictest](../usage/publish-cyclictest.md) explains
`--publish`, existing bundles, and retries. Publication targets the external
`rt-results` catalog, not Prometheus. Its dashboard is
`Cyclictest Scheduler Latency Prototype` (`rt-cyclictest-prototype`); when your
server provisions it and you forward Grafana:

```bash
ssh -N -L 3002:127.0.0.1:3000 RESULTS_USER@RESULTS_HOST
```

Open `http://127.0.0.1:3002/d/rt-cyclictest-prototype/cyclictest-scheduler-latency-prototype`.
The `run` variable selects one `run_uid`; switch it to compare per-CPU summaries
or compare catalog rows. The raw bundle remains primary evidence. Use
[cyclictest comparison methodology](../methodology/cyclictest-comparisons.md)
for controlled repeated experiments.
