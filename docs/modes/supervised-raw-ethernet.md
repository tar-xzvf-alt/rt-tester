# Supervised Raw-Ethernet Режим

Этот режим измеряет полный путь Arduino, controller, raw Ethernet supervisor и
runtime. Основной интерфейс — `rt-tester-run-stand`; runner единолично управляет
readiness barrier, workload, receiver и trace collection.

```text
PC receiver -> Arduino -> controller GPIO -> raw Ethernet
             <- Arduino <- controller GPIO <- supervisor/runtime response
```

Для baseline без supervisor используйте [Standalone GPIO](standalone-gpio.md).
Для scheduler-only измерений используйте [Linux Benchmarks](linux-benchmarks.md).

## Стандартный запуск измерения

Основной пользовательский путь для raw-Ethernet стенда — пакетный wrapper и
один установленный конфиг:

```bash
rt-tester-run-stand \
    --config /usr/share/rt-tester-tools/configs/stands/rockpi-plc-visionfive2-controller.conf
```

Этот конфиг описывает роли плат:

```text
runtime/supervisor board = Beremiz runtime + alt-rt-supervisor
controller board         = GPIO controller side
```

Без дополнительных параметров runner показывает пользовательский summary:
stand и session ID, план теста, этапы подготовки, ссылку Grafana, каждую
завершенную группу и итоговые аномалии. Ссылка с выбранным `session_id`
печатается сразу после запуска Grafana, поэтому dashboard можно открыть во время
измерения.

Полный список команд и foreground-вывод включается отдельно:

```bash
rt-tester-run-stand \
    --config /usr/share/rt-tester-tools/configs/stands/rockpi-plc-visionfive2-controller.conf \
    --verbose
```

В обычном режиме ошибка всё равно содержит команду, exit status и до 40 последних
строк дочернего вывода. Prometheus, Grafana, trace exporters, supervisor,
runtime и controller продолжают писать в log files из stand config; `--verbose`
не заменяет эти файлы, а показывает команды их запуска.

## Pipeline работы стенда

`run_stand_measurement.py` выполняет полный цикл стенда:

1. Проверяет сеть ПК через command из `[pc] network-check`, если он задан.
   Конкретная топология сети задается выбранным stand config и network-check
   helper, а не runner code.
2. Синхронизирует часы runtime и controller boards с текущего ПК через
   `date -u -s`. Это нужно для trace metrics с explicit timestamps. Если время
   обслуживается отдельно, шаг можно отключить через `--skip-time-sync`.
3. Запускает target preflight по SSH: `rt-supervisor/scripts/preflight_stand.sh`
   на runtime/supervisor board и `rt-controller/scripts/preflight_stand.sh` на
   controller board.
   Эти проверки валидируют stand config, интерфейс, clock sanity, socket buffers,
   а controller side дополнительно проверяет GPIO/libgpiod. Если
   `[measurement] target-stress = on`, runner также проверяет наличие `stress-ng`
   на runtime-плате.
4. При `--build` пересобирает заранее размещенные remote source trees из
   `[supervisor] repo` и `[controller] repo` с board names из config. Runner не
   имеет опции `--deploy` и не копирует эти trees.
5. Стартует trace exporters на обеих платах. Они читают JSONL trace files и
   отдают Prometheus metrics на `:9201`.
6. Стартует локальный Prometheus на `127.0.0.1:9091`. Он scrape-ит PC receiver,
   оба trace exporters и `node_exporter` runtime-платы.
7. Для текущего packaged profile поднимает SSH tunnel к central Grafana на
   `127.0.0.1:13000`. Локальная managed Grafana на `3001` используется только
   профилями с `grafana-managed = true`.
8. Если `[measurement] target-stress = on`, запускает CPU+memory нагрузку на
   runtime-плате. По умолчанию используется
   `stress-ng --cpu 0 --vm 0 --vm-bytes 85% --timeout 0`; команду, pidfile и log
   можно переопределить в секции `[stress]`.
9. Запускает `alt-rt-supervisor` на runtime/supervisor board. Supervisor открывает
   raw Ethernet interface из `[supervisor] iface`, создает `/dev/shm/shmem_input`
   и `/dev/shm/shmem_output`, затем через `-r` стартует runtime wrapper.
10. Запускает `controller-emu -b BOARD` на controller board. Controller слушает
   GPIO input от Arduino, формирует BETH request, добавляет trace metadata и
   отправляет full `96 KiB` raw-Ethernet request на runtime/supervisor board.
11. Запускает `receiver.py --start --exit-on-stop` на ПК. Receiver командует
   Arduino по serial, пишет SQLite DB и отдает `arduino_latency_*` metrics на
   `127.0.0.1:9101`.
12. Во время measurement Arduino генерирует GPIO pulse, `controller-emu` отправляет
    raw-Ethernet request, `alt-rt-supervisor` передает payload в Beremiz через
    shared memory/futex, получает response и возвращает его controller-у, а
    controller выставляет GPIO output обратно на Arduino.
13. После Arduino auto-stop runner останавливает target processes и runtime stress,
    импортирует
    trace metrics из Prometheus в SQLite, проверяет group alignment/log anomalies
    и печатает ссылку Grafana с текущим `session_id`.

Перед запуском receiver и сразу после measurement runner снимает network-health
snapshots на runtime и controller платах: `/proc/net/dev`, `/proc/net/softnet_stat`
и `ethtool -S <iface>` если `ethtool` доступен. В summary печатается delta по
traffic counters и рост drops/errors/CRC/overflow/underflow. Эти counters
считаются measurement anomaly. Host-wide `softnet.time_squeeze` не привязан к
конкретному interface и сам по себе не означает потерю пакетов, поэтому он
печатается как per-CPU warning и не меняет результат measurement.

Runner также передает controller ожидаемое число measurement groups. Новые
GPIO edges после этого окна записываются controller в log как timestamped
`trace out-of-window edge` warnings для диагностики startup/shutdown pulses.

При cleanup runner ждёт завершения PID-file supervisor/controller до трёх секунд
и только затем удаляет shared-memory names или запускает новый экземпляр. Это
не допускает одновременную работу старого и нового runtime ABI.

Example stand `configs/stands/rockpi-plc-visionfive2-controller.conf` задает
такую текущую лабораторную топологию:

```text
rockpi      = Beremiz runtime + alt-rt-supervisor
visionfive2 = GPIO controller side
```

Полезные опции:

```bash
# Короткий smoke на 10 групп
rt-tester-run-stand \
    --config /usr/share/rt-tester-tools/configs/stands/rockpi-plc-visionfive2-controller.conf \
    --groups 10

# Такой же smoke с CPU+memory stress-ng на runtime-плате
rt-tester-run-stand \
    --config /usr/share/rt-tester-tools/configs/stands/rockpi-plc-visionfive2-controller-stress.conf \
    --groups 10

# Проверить команды без запуска стенда
rt-tester-run-stand \
    --config /usr/share/rt-tester-tools/configs/stands/rockpi-plc-visionfive2-controller.conf \
    --dry-run

# Полная диагностика команд и foreground-процессов
rt-tester-run-stand \
    --config /usr/share/rt-tester-tools/configs/stands/rockpi-plc-visionfive2-controller.conf \
    --groups 2 \
    --verbose

# Пересобрать вручную размещенные и настроенные source trees
rt-tester-run-stand \
    --config /path/to/source-stand.conf \
    --build
```

Пакетные config используют установленные `/usr/share/rt-supervisor`,
`/usr/share/rt-controller`, `/usr/bin/alt-rt-supervisor` и
`/usr/bin/controller-emu`. Стандартный config также использует
`/usr/bin/runtime` из отдельного target-пакета
`rt-supervisor-runtime-example`; в них нет обязательного для сборки поля `build`.
Поэтому `--build` не является готовой возможностью пакетной конфигурации. Нужно
вручную разместить source trees на обеих платах и изменить `repo`, `build` и
`binary` в собственной копии config. У supervised runner нет `--deploy`.

После завершения measurement target-процессы (`alt-rt-supervisor`, Beremiz,
`controller-emu`) останавливаются автоматически. Prometheus, Grafana и remote
trace exporters остаются запущенными, чтобы Grafana продолжала видеть результаты.
Остановить их можно так:

```bash
rt-tester-run-stand \
    --config /usr/share/rt-tester-tools/configs/stands/rockpi-plc-visionfive2-controller.conf \
    --stop-observability
```

Текущий centrally managed profile печатает Grafana URL перед measurement и
повторяет его в итогах:

```text
Grafana: http://127.0.0.1:13000/d/rt-trace-stages?var-session_id=1782751117
```

Prometheus URL является диагностической деталью и печатается при `--verbose`.

## Просмотр latency и trace breakdown в Grafana

Основной dashboard для stand runs:

```text
http://127.0.0.1:13000/d/rt-trace-stages?var-session_id=<session_id>
```

Он называется `RT Trace Stage Breakdown` и показывает Arduino latency вместе с
trace-разбиением одного и того же запуска:

- самый верх dashboard — нагрузка runtime-платы на CPU/memory %;
- сразу под ней — network RX/TX throughput из `node_exporter` в bytes/sec;
- далее — end-to-end latency от Arduino/receiver;
- середина — обычные controller/supervisor stages без retry;
- низ dashboard — все `retry_*` панели.

Все панели рисуются как time series по одному wall-clock времени Prometheus.
Линии ступенчатые: значение группы держится на графике до появления следующей
группы. Это специально сделано одинаково для Arduino latency и trace stages,
чтобы временные интервалы на оси X совпадали.

Для live dashboard используются метрики `rt_trace_stage_latest_us` и
`rt_trace_stage_latest_count`: они показывают последний завершенный trace group
для выбранного `session_id`. Исторические group-level метрики
`rt_trace_stage_us` и `rt_trace_stage_count` остаются доступны для импорта в
SQLite и post-hoc анализа по `group_index`.

Для проверки Grafana не используйте одногрупповые smoke runs: receiver может
завершиться сразу после первой группы, и Prometheus не всегда успевает scrape
`arduino_latency_*` после появления group metrics. Для dashboard smoke используйте
минимум несколько групп, обычно `--groups 10`.

Runtime-board load берется из `runtime_node_exporter`. По умолчанию runner
строит target из `[supervisor] host` как `<supervisor-ip>:9100`. Если
`node_exporter` слушает на другом адресе, задайте в `[observability]`:

```ini
runtime-node-exporter-target = 10.43.0.2:9100
```

Network RX/TX показываются как `rate(node_network_*_bytes_total)` в bytes/sec,
без нормализации через `node_network_speed_bytes`.

Если measurement завершился, но в SQLite появились события кроме `start`/`stop`,
в логах target-процессов есть `ERR`/`WARN`/CRC/timeout, trace group count не
совпадает с receiver group count, trace-метрики противоречат Arduino latency или
network-health counters выросли по drops/errors, скрипт печатает
`Measurement completed with anomalies` и завершает работу с кодом `2`. При этом
БД, Prometheus и ссылка Grafana остаются доступными для разбора причины.

Сообщение `Arduino latency contradicts imported trace metrics` означает, что
один обязательный trace stage уже дольше максимальной задержки, измеренной
Arduino. Обычно это указывает на неверную проводку, прямой loopback/crosstalk
между Arduino `D7` и `D20` или отсутствие общего GND.

Сообщение `trace group count does not match receiver groups` означает, что
controller/supervisor увидели больше или меньше GPIO/Ethernet cycles, чем
Arduino/receiver сохранили как measurement groups. Частая причина — лишние edges
на controller GPIO input или trace, стартовавший до фактического measurement
window Arduino.

По умолчанию stand config передаёт полный 96 KiB supervisor slot. Опциональный
параметр `[transport] payload-size` прокидывается как
`RT_TRANSPORT_PAYLOAD_SIZE` и может использоваться только для специальных
compact-payload экспериментов.
Параметр `[transport] response-timeout-ms` прокидывается как
`RT_RESPONSE_TIMEOUT_MS` и задаёт controller-side timeout ожидания response перед
retry.
Параметры `[transport] retransmit-timeout-ms` и
`[transport] gap-nack-retries` прокидываются как `RT_RETRANSMIT_TIMEOUT_MS` и
`RT_GAP_NACK_RETRIES`; они задают интервал между NACK повторами и число NACK
попыток перед abandon incomplete raw-Ethernet session.

Target preflight настраивает `net.core.rmem_max` и `net.core.wmem_max` минимум на
4 MiB, чтобы raw-socket buffers для full 96 KiB payload не были silently capped.
Если в логах появляются `requested retransmit`, это transport-level
восстановление отдельных raw-Ethernet frames. Если появляются `retry_*` stages,
это уже controller-side retry всего request/response cycle после истечения
`RT_RESPONSE_TIMEOUT_MS`.

## Связанные Документы

- [Dependencies](../reference/dependencies.md): PC, runtime, controller и Arduino packages.
- [Central Observability](../observability/central.md): remote write, SSH tunnel и server deployment.
- [PC Receiver](../usage/receiver.md): collection, trace import и integrity.
- [Analysis and Reports](../usage/analysis-and-reports.md): post-processing SQLite sessions.
- [GPIO Methodology](../methodology/gpio-measurements.md): воспроизводимые comparison runs.
