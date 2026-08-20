# Standalone GPIO Режим

Standalone GPIO режим измеряет базовую задержку платы без `rt-supervisor`,
raw Ethernet и Beremiz/runtime слоя.

```text
PC receiver.py -> Arduino Mega -> GPIO input target board
                              <- GPIO output target board <- handler
```

Default package workflow использует userspace `rt-handler`. Экспериментальные
profiles также поддерживают kernelspace `rt_gpio_responder`. Source of truth
находится в соответствующих target repositories; в `rt-tester` target C-код не
дублируется.

## Когда Использовать

- Для baseline измерения `Arduino -> target GPIO -> Arduino`.
- Для проверки wiring и GPIO latency перед supervised raw-Ethernet стендом.
- Для сравнения standalone GPIO latency с цепочкой `controller-emu -> supervisor -> runtime`.

## Что Не Используется

- `alt-rt-supervisor`.
- `controller-emu`.
- Beremiz или stub runtime.
- Legacy импорт `/var/log/soc_metrics.log`.
- Секция `[soc]` в receiver config.

CPU/memory метрики собираются через `node_exporter` и Prometheus. Runner не
читает и не импортирует текстовый metrics log, который исторически мог писать
`rt-handler`; в config он направляется в `/dev/null`.

## Конфиг Стенда

Пример для VisionFive 2:

```text
/usr/share/rt-tester-tools/configs/stands/visionfive2-standalone-gpio.conf
```

Путь выше относится к установленному `rt-tester-tools`. В checkout тот же файл
доступен как `configs/stands/visionfive2-standalone-gpio.conf`.

Ключевые поля:

```ini
[target]
host = root@10.42.0.211
label = visionfive2
board = starfive
binary = /usr/sbin/rt-handler
args = -b {board}
workdir = /
metrics-log = /dev/null
housekeeping-cpus = 0
```

`board = starfive` здесь означает runtime profile в `rt-handler` для
VisionFive 2. User-facing имя стенда и target-board остаются `visionfive2`.

## Запуск

### Userspace Package

Запустить measurement с установленным RPM-пакетом `rt-handler` на target:

```bash
rt-tester-run-gpio \
    --config /usr/share/rt-tester-tools/configs/stands/visionfive2-standalone-gpio.conf
```

Штатный пакетный config запускает `/usr/sbin/rt-handler` и не требует сборки.
Standalone runner поддерживает оба source-сценария:

- `--deploy` копирует локальный tree из `rt-handler-local` в target `repo`;
- `--build` выполняет `make` в `<repo>/src` без копирования исходников;
- `--deploy --build` сначала копирует, затем собирает.

Для source-запуска нужно работать с собственной копией config и задать
`rt-handler-local`/`repo`, `binary = /root/rt-handler/src/rt-handler` и
`workdir = /root/rt-handler/src`. Один `--build` требует, чтобы source tree уже
был размещен на target вручную или предыдущим `--deploy`.

### Kernelspace Module

Kernelspace profile задает:

```ini
[target]
execution-mode = kernelspace
module = rt_gpio_responder
```

В этом режиме runner проверяет module, выполняет `modprobe`, проверяет IRQ и не
разрешает `--deploy` или `--build`. Пакетные VisionFive 2 comparison profiles
покрывают userspace/kernelspace, RT/non-RT и idle/stressed combinations.

Короткий smoke:

```bash
rt-tester-run-gpio \
    --config /usr/share/rt-tester-tools/configs/stands/visionfive2-standalone-gpio.conf \
    --groups 3
```

Проверить команды без выполнения:

```bash
rt-tester-run-gpio \
    --config /usr/share/rt-tester-tools/configs/stands/visionfive2-standalone-gpio.conf \
    --dry-run
```

Только подготовить target без запуска Arduino measurement:

```bash
rt-tester-run-gpio \
    --config /usr/share/rt-tester-tools/configs/stands/visionfive2-standalone-gpio.conf \
    --prepare-only
```

После запуска runner:

1. проверяет SSH до target;
2. проверяет, что Arduino serial port доступен;
3. опционально синхронизирует время target;
4. для userspace при `--deploy` копирует внешний `rt-handler` на target;
5. для userspace при `--build` запускает `make` в source tree на target;
6. останавливает старые userspace handler/stress процессы или подготавливает
   выбранный kernel module;
7. стартует Prometheus на `127.0.0.1:9092`, если он не запущен;
8. подготавливает Grafana согласно profile: current profile использует central
   tunnel на `13000`, а local managed profile может использовать `3002`;
9. стартует выбранный userspace handler или загружает kernel module;
10. печатает userspace log или kernel module/IRQ diagnostics;
11. переводит `node_exporter` в `SCHED_OTHER` и пинит его на housekeeping CPU;
12. запускает `receiver.py --start --exit-on-stop`;
13. печатает handler, `node_exporter` и Prometheus diagnostics;
14. проверяет SQLite summary.

## Grafana

Текущий packaged profile использует central Prometheus/Grafana через SSH tunnel
и печатает ссылку вида:

```text
Grafana: http://127.0.0.1:13000/d/rt-standalone-gpio?var-session_id=<session_id>
```

Для этого нужны доступ к `wetgrape.su` и configured central SSH identity. Без
central infrastructure используйте `--no-prometheus --no-grafana` или создайте
profile с local observability. Если `grafana-managed = true`, standalone runner
может управлять отдельной локальной Grafana на configured port, обычно `3002`.

Dashboard называется `RT Standalone GPIO` и находится в папке `RT GPIO`. Он
показывает:

- Arduino latency: avg/max/min;
- Arduino jitter;
- CPU/memory target-платы из `node_exporter`.

Все три панели расположены друг под другом и используют общий time range
dashboard, поэтому ось X синхронизирована. В dashboard есть переменные `board`
и `session_id`; latency/jitter панели используют thresholds для быстрого поиска
выбросов.

Остановить observability processes/tunnel, которыми управляет runner:

```bash
rt-tester-run-gpio \
    --config /usr/share/rt-tester-tools/configs/stands/visionfive2-standalone-gpio.conf \
    --stop-observability
```

## node_exporter Priority

`node_exporter` не должен конкурировать с real-time GPIO path. Runner не повышает
его приоритет; наоборот, он переводит все TID `node_exporter` в `SCHED_OTHER` и
закрепляет их на `housekeeping-cpus` из config.

## Wiring

Arduino Mega использует тот же физический протокол, что и остальные измерения:

- Arduino pin 7 -> GPIO input target board;
- GPIO output target board -> Arduino pin 20;
- общий GND обязателен.

GPIO line numbers задаются в `/etc/rt-handler/boards.d/*.conf` и во встроенных
profiles `rt-handler`.

## Результаты

Основные данные сохраняются в SQLite через обычный receiver pipeline:

- `groups`;
- `latencies`;
- `events`;
- `soc_metrics`, если Prometheus/node_exporter доступны.

Result paths задаются конкретным profile: smoke configs могут использовать
`/tmp`, а comparison configs используют persistent state directory. Receiver
пишет внутренние logs и `metrics_all_groups.log` в XDG state directory; этот
путь можно заменить через `RT_TESTER_STATE_DIR`. Общая карта находится в
[Runtime Paths](../reference/runtime-paths.md).

Для анализа из checkout используется `src/pc-receiver/plot_statistics.py`. Эта
source-only утилита не входит в RPM `rt-tester-tools`.

Сводка baseline и reference supervised-сессий хранится в
[Standalone GPIO Baseline](../results/standalone-gpio-baseline.md).
