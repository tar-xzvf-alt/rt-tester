# Linux Responsiveness Benchmarks

Linux benchmark mode запускает уже установленный `cyclictest` на target по SSH.
Он не использует Arduino, GPIO, receiver DB или Prometheus remote write.

## Когда Использовать

- измерить scheduler wake-up latency PREEMPT_RT kernel;
- сравнить idle и controlled stress;
- отделить scheduler behavior от GPIO hardware path;
- сравнить kernels, governors и power-management settings.

## Data Flow

```text
rt-tester-run-linux-benchmark on PC
  -> SSH target
  -> /usr/bin/cyclictest
  -> native JSON, histogram and logs in target /tmp
  -> SCP to local .<run_uid>.partial
  -> validation and manifest.json
  -> atomic rename to finalized <run_uid> bundle
  -> optional publication to rt-results
```

Finalized bundle предназначен оставаться неизменным. Manifest перечисляет все
файлы, размеры и SHA256. Publisher отклоняет undeclared или измененные файлы.

## Target Prerequisites

```bash
apt-get install linux-rt-tests stress-ng openssh-server
```

`stress-ng` нужен только stressed profile. Начиная с `rt-handler-0.1.8-alt1`,
оба benchmark-пакета являются его runtime dependencies.

Runner проверяет SSH, executable cyclictest, expected kernel, package version и
наличие stress-ng. Ошибка preflight не создает complete bundle.

## Packaged Profiles

```text
/usr/share/rt-tester-tools/configs/stands/visionfive2-rt-cyclictest-idle.conf
/usr/share/rt-tester-tools/configs/stands/visionfive2-rt-cyclictest-stressed.conf
```

Эти профили описывают текущий лабораторный VisionFive 2 и содержат конкретные
адреса, kernel version и server settings. Для другого стенда скопируйте профиль
и отредактируйте его.

## Запуск

Idle:

```bash
rt-tester-run-linux-benchmark \
  --config /path/to/cyclictest-idle.conf \
  --duration 10m
```

Stress:

```bash
rt-tester-run-linux-benchmark \
  --config /path/to/cyclictest-stressed.conf \
  --duration 10m
```

Показать generated cyclictest command без запуска:

```bash
rt-tester-run-linux-benchmark \
  --config /path/to/cyclictest.conf \
  --print-command
```

Изменить каталог bundles:

```bash
rt-tester-run-linux-benchmark \
  --config /path/to/cyclictest.conf \
  --output-root ~/.local/state/rt-tester/my-series
```

## Параметры Cyclictest

Текущие VisionFive 2 profiles используют один FIFO thread на online CPU:

```text
--default-system --smp --policy=fifo --priority=95
--interval=1000 --distance=0 --mlockall
```

Stressed profile запускает отдельную process group:

```text
stress-ng --cpu 4 --cpu-method int64 \
  --vm 1 --vm-bytes 70% --vm-keep --timeout 0
```

Runner останавливает только созданную process group и сохраняет stress log.

## Результат

Complete bundle содержит как минимум:

- `manifest.json`;
- `cyclictest.json`;
- `histogram.txt`;
- `stdout.log` и `stderr.log`;
- `stress.log` и `stress.pid` для stressed run.

Manifest фиксирует target kernel, architecture, governors, tool packages,
command, workload, cycles, histogram overflow и checksums.

Для автоматической отправки используйте [Publishing Cyclictest](../usage/publish-cyclictest.md).
Для controlled idle/stress comparison используйте [Cyclictest Comparisons](../methodology/cyclictest-comparisons.md).

## Просмотр Результатов

Локально summary и target metadata находятся в `manifest.json`, а per-thread
statistics и histogram — в native `cyclictest.json`. После публикации central
dashboard называется `Cyclictest Scheduler Latency Prototype`.

SSH tunnel к текущему project server:

```bash
ssh -N -L 13000:127.0.0.1:3000 -p 228 root@wetgrape.su
```

Dashboard:

```text
http://127.0.0.1:13000/d/rt-cyclictest-prototype/cyclictest-scheduler-latency-prototype
```

Catalog показывает все runs и позволяет фильтровать workload. Текущая dashboard
variable `run` выбирает один `run_uid`: per-CPU summary и histogram относятся к
этому run. Для сопоставления нескольких runs переключайте selection или
сравнивайте строки catalog. Raw bundle остается первичным артефактом.
