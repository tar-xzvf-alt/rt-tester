# Prometheus и Grafana

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
7. Стартует локальную Grafana на `127.0.0.1:3001` с provisioning из `grafana/`.
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
traffic counters и рост drops/errors/CRC/overflow/underflow/softnet `time_squeeze`.
Ненулевой рост таких counters считается measurement anomaly.

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

# Пересобрать вручную размещенные и настроенные source trees
rt-tester-run-stand \
    --config /path/to/source-stand.conf \
    --build
```

Пакетные config используют установленные `/usr/share/rt-supervisor`,
`/usr/share/rt-controller`, `/usr/bin/alt-rt-supervisor` и
`/usr/bin/controller-emu`; в них нет обязательного для сборки поля `build`.
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

Скрипт печатает итоговые URL, например:

```text
Prometheus: http://127.0.0.1:9091
Grafana: http://127.0.0.1:3001/d/rt-trace-stages?var-session_id=1782751117
```

## Просмотр latency и trace breakdown в Grafana

Основной dashboard для stand runs:

```text
http://127.0.0.1:3001/d/rt-trace-stages?var-session_id=<session_id>
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
network-health counters выросли по drops/errors/softnet squeeze, скрипт печатает
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

## Зависимости

### Обязательные Зависимости RPM На ПК

`rt-tester-tools` требует `python3`, `python3-module-serial`,
`python3-module-requests`, `/bin/sh`, `openssh-clients`, `rsync` и `coreutils`.
Этого достаточно для установленных команд, но внешние сервисы observability и
target software устанавливаются отдельно.

### Observability И Source-Only Анализ На ПК

```bash
apt-get install prometheus grafana
```

| Пакет | Назначение |
|-------|-----------|
| `prometheus` | Сервер сбора метрик |
| `grafana` | Визуализация (опционально) |

Для source-only `plot_statistics.py` нужны `python3-module-pandas`,
`python3-module-numpy` и `python3-module-matplotlib`. Пакет
`python3-module-paramiko` нужен только legacy SSH SoC tooling, которое не входит
в RPM. Текущий встроенный metrics server не требует
`python3-module-prometheus_client`.

### Target Runtime

```bash
apt-get install prometheus-node_exporter openssh-server
```

Дополнительно устанавливаются `rt-handler` для standalone или
`rt-supervisor`/`rt-controller` для supervised. `stress-ng` нужен только при
`target-stress = on`.

### Target Source Build

Build-зависимости определяются target-проектом и не нужны при запуске
установленных binaries. Для сборки `rt-handler` нужны:

```bash
apt-get install gcc make glibc-devel libgpiod-devel pkg-config
```

Supervised `--build` требует вручную размещенных source trees и настроенных
`repo`, `build`, `binary`; runner не предоставляет `--deploy`.

### Arduino

```bash
apt-get install arduino-core avr-gcc
```

| Пакет | Назначение |
|-------|-----------|
| `arduino-core` | Ядро Arduino |
| `avr-gcc` | Компилятор для AVR (Arduino Mega) |

## Запуск Prometheus (systemd)

Этот раздел описывает ручную настройку из source checkout. Файл
`prometheus/prometheus.yml` не входит в RPM `rt-tester-tools`; пакетный runner
генерирует локальный config в `/tmp` из stand config.

```bash
sudo cp prometheus/prometheus.yml /etc/prometheus/prometheus.yml
sudo systemctl restart prometheus
```

Конфигурация в `prometheus/prometheus.yml`:
- Scrape interval: 500ms
- node_exporter на SoC: `<IP_SOC>:9100`
- receiver metrics server: `localhost:9101`
- Retention: размерный (10GB) в systemd override

## Импорт дашборда Grafana

Ниже используется legacy dashboard из source checkout. Файл
`grafana/rt-tester-dashboard.json` не входит в RPM; пакет содержит dashboards и
provisioning, которые runners используют из `/usr/share/rt-tester-tools/grafana`.

```bash
curl -X POST http://admin:admin@localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d "{\"dashboard\":$(cat grafana/rt-tester-dashboard.json),\"overwrite\":true}"
```
