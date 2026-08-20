# Linux Responsiveness Benchmarks Prototype

The prototype runs cyclictest directly on a target over SSH and stores an
immutable result bundle. It does not use Arduino, alter the GPIO databases, or
install files from the RPM package.

VisionFive 2 idle smoke:

```sh
python3 scripts/run_linux_benchmark.py \
  --config configs/stands/visionfive2-rt-cyclictest-idle.conf
```

VisionFive 2 stress smoke:

```sh
python3 scripts/run_linux_benchmark.py \
  --config configs/stands/visionfive2-rt-cyclictest-stressed.conf
```

Both configs run one FIFO cyclictest thread per online CPU, preserve the
native JSON and histogram, and record kernel, architecture, CPU topology,
governors, command line, package version, checksums, and workload type in
`manifest.json`.

The 10-second duration validates the pipeline only. It is not long enough to
characterize worst-case scheduler latency. Public comparison runs should use
the same profile and substantially longer durations.

The stress config starts a dedicated stress-ng process group and stops only
that group. It does not use broad `pkill` cleanup.
