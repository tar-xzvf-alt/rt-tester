# Cyclictest comparison methodology

[Русский](../ru/methodology/cyclictest-comparisons.md)

Compare idle and stressed runs with the same benchmark settings, kernel, CPU
topology, and power policy. Ten-second runs check the collection pipeline;
they do not characterize worst-case latency.

## Recommended series

1. Smoke each adapted profile.
2. Fix CPU frequency or explicitly make DVFS (dynamic voltage/frequency scaling)
   part of the investigation.
3. Use ABBA ordering: idle, stress, stress, idle.
4. Run for at least ten minutes and repeat the series at least three times.
5. Check histogram overflow, target state, and stress cleanup.
6. Compare per-run and per-CPU mean, p95, p99, and maximum. Disclose overflow and
   do not derive a whole distribution from a truncated histogram without accounting
   for it.
7. Preserve every finalized bundle. Do not conclude from one maximum.

## VisionFive 2 frequency control example

The historical stand used shared `policy0` for CPUs 0–3 and available frequencies
`375000 500000 750000 1500000` kHz. Verify these on **your** kernel/board first.
Replace `TARGET_HOST`; commands below change privileged target state. Record the
original values in your experiment notes and arrange restoration even after a
failed run.

```bash
ssh root@TARGET_HOST '
P=/sys/devices/system/cpu/cpufreq/policy0
for f in scaling_driver affected_cpus scaling_available_frequencies \
    scaling_governor scaling_min_freq scaling_max_freq scaling_cur_freq; do
    printf "%s=" "$f"
    read -r value < "$P/$f"
    printf "%s\n" "$value"
done
'
```

If 1.5 GHz is supported, fix its policy:

```bash
ssh root@TARGET_HOST '
set -eu
P=/sys/devices/system/cpu/cpufreq/policy0
printf "%s\n" performance > "$P/scaling_governor"
printf "%s\n" 1500000 > "$P/scaling_max_freq"
printf "%s\n" 1500000 > "$P/scaling_min_freq"
'
```

Check governor, min/max/current frequency before and after each run. Frequency
settings do not eliminate thermal throttling: control cooling and record temperature.

```bash
rt-tester-run-linux-benchmark --config ./idle.conf --duration 10m
rt-tester-run-linux-benchmark --config ./stress.conf --duration 10m
rt-tester-run-linux-benchmark --config ./stress.conf --duration 10m
rt-tester-run-linux-benchmark --config ./idle.conf --duration 10m
```

Add `--publish` only when your independent results server is configured.
Restore the **recorded original** min/max/governor afterward. The historical
defaults were min `375000`, max `1500000`, governor `schedutil`; do not assume
those values on another installation.

## Interpretation

If idle/stress values converge after fixing frequency, the original difference
depended on DVFS. If stress remains faster, investigate CPU idle states,
DDR/interconnect devfreq, and IRQ placement separately. If stress worsens p95/p99
at the same frequency, scheduler/cache/memory contention are candidate mechanisms,
not automatically proven causes.

Long runs have more opportunity to reveal rare outliers, so maxima from different
durations are not directly comparable. PREEMPT_RT describes kernel behavior,
not an experimentally established guaranteed deadline. See
[benchmark execution](../modes/linux-benchmarks.md) and
[publication](../usage/publish-cyclictest.md).
