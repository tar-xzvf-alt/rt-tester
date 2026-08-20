# Cyclictest Comparison Methodology

## Цель

Idle и stress нужно сравнивать при одинаковых benchmark parameters, kernel,
CPU topology и power-management policy. Короткие 10-second runs проверяют
pipeline, но не характеризуют worst-case latency.

## Рекомендуемая Серия

1. Выполните smoke test каждого profile.
2. Зафиксируйте CPU frequency или явно оставьте DVFS предметом исследования.
3. Используйте ABBA order: idle, stress, stress, idle.
4. Запускайте не менее 10 минут и повторите серию минимум три раза.
5. Проверяйте histogram overflow и stress cleanup.
6. Сравнивайте per-run и per-CPU mean, p95, p99 и max.
7. Не делайте вывод по одному maximum.

## VisionFive 2 Fixed Frequency

На текущем стенде CPU 0-3 используют общую `policy0`. Доступные частоты:

```text
375000 500000 750000 1500000 kHz
```

Запишите исходное состояние:

```bash
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

Зафиксируйте 1.5 GHz:

```bash
ssh root@10.42.0.211 '
set -eu
P=/sys/devices/system/cpu/cpufreq/policy0
printf "%s\n" performance > "$P/scaling_governor"
printf "%s\n" 1500000 > "$P/scaling_max_freq"
printf "%s\n" 1500000 > "$P/scaling_min_freq"
'
```

Перед и после каждого run проверьте, что governor равен `performance`, а
`scaling_min_freq`, `scaling_max_freq` и `scaling_cur_freq` равны `1500000`.
Это не гарантирует отсутствие thermal throttling, поэтому контролируйте cooling
и температуру.

Запустите ABBA:

```bash
rt-tester-run-linux-benchmark --config /path/to/idle.conf --duration 10m --publish
rt-tester-run-linux-benchmark --config /path/to/stress.conf --duration 10m --publish
rt-tester-run-linux-benchmark --config /path/to/stress.conf --duration 10m --publish
rt-tester-run-linux-benchmark --config /path/to/idle.conf --duration 10m --publish
```

Восстановите текущие defaults VisionFive 2 даже после ошибки:

```bash
ssh root@10.42.0.211 '
set -eu
P=/sys/devices/system/cpu/cpufreq/policy0
printf "%s\n" 375000 > "$P/scaling_min_freq"
printf "%s\n" 1500000 > "$P/scaling_max_freq"
printf "%s\n" schedutil > "$P/scaling_governor"
'
```

## Интерпретация

Если idle/stress сближаются после фиксации частоты, исходная разница зависела
от DVFS. Если stress остается быстрее, отдельно исследуйте CPU idle states,
DDR/interconnect devfreq и IRQ placement. Если stress ухудшает p95/p99 при
одинаковой частоте, это отражает scheduler, cache и memory contention.

Длинный run чаще обнаруживает редкие outliers, поэтому maximum нельзя напрямую
сравнивать между сериями разной длительности.
