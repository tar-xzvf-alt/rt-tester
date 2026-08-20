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

## Fixed-frequency idle and stress comparison

Frequency control must be applied before both runs so that stress-induced DVFS
does not bias the comparison. On the VisionFive 2 stand, CPUs 0-3 share
`policy0`; its available frequencies are 375000, 500000, 750000 and 1500000
kHz. Run the comparison as root on the target.

Record the initial state:

```sh
ssh root@10.42.0.211 '
P=/sys/devices/system/cpu/cpufreq/policy0
for f in scaling_driver affected_cpus scaling_available_frequencies \
    scaling_governor scaling_min_freq scaling_max_freq scaling_cur_freq; do
    printf "%s=" "$f"
    read -r value < "$P/$f"
    printf "%s\n" "$value"
done
'
```

Lock the shared policy to 1.5 GHz:

```sh
ssh root@10.42.0.211 '
set -eu
P=/sys/devices/system/cpu/cpufreq/policy0
printf "%s\n" performance > "$P/scaling_governor"
printf "%s\n" 1500000 > "$P/scaling_max_freq"
printf "%s\n" 1500000 > "$P/scaling_min_freq"
for f in scaling_governor scaling_min_freq scaling_max_freq scaling_cur_freq; do
    printf "%s=" "$f"
    read -r value < "$P/$f"
    printf "%s\n" "$value"
done
'
```

All three frequency values must report 1500000. Run longer measurements using
the otherwise identical packaged profiles:

```sh
rt-tester-run-linux-benchmark \
  --config /usr/share/rt-tester-tools/configs/stands/visionfive2-rt-cyclictest-idle.conf \
  --duration 10m

rt-tester-run-linux-benchmark \
  --config /usr/share/rt-tester-tools/configs/stands/visionfive2-rt-cyclictest-stressed.conf \
  --duration 10m
```

Check `scaling_cur_freq` before and after every run. Use an ABBA sequence
(`idle`, `stress`, `stress`, `idle`) and repeat it at least three times to
reduce ordering and thermal bias. A fixed cpufreq policy does not prevent
thermal throttling, so keep target cooling and ambient conditions constant.

Restore the current VisionFive 2 defaults after the series:

```sh
ssh root@10.42.0.211 '
set -eu
P=/sys/devices/system/cpu/cpufreq/policy0
printf "%s\n" 375000 > "$P/scaling_min_freq"
printf "%s\n" 1500000 > "$P/scaling_max_freq"
printf "%s\n" schedutil > "$P/scaling_governor"
for f in scaling_governor scaling_min_freq scaling_max_freq scaling_cur_freq; do
    printf "%s=" "$f"
    read -r value < "$P/$f"
    printf "%s\n" "$value"
done
'
```

If idle and stress converge at a fixed frequency, CPU DVFS caused most of the
original difference. If stress remains faster, repeat the fixed-frequency
series with deep CPU idle states disabled to isolate wake-up latency from
frequency scaling.
