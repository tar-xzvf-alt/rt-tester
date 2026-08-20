# PC Receiver

Receiver управляет Arduino measurement session, принимает group JSON, собирает
SoC metrics через Prometheus и сохраняет session SQLite DB.

- Source: [`src/pc-receiver`](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/pc-receiver)
- SQLite reference: [SQLite Schema](../reference/sqlite-schema.md)
- Post-processing: [Analysis and Reports](analysis-and-reports.md)
- Dependencies: [Dependencies](../reference/dependencies.md)

RPM содержит receiver, trace importer и trace summary. Plotting и database
merge остаются source-only tools.

## Runtime State

Receiver logs и `metrics_all_groups.log` находятся в:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/rt-tester
```

`RT_TESTER_STATE_DIR` заменяет этот каталог, но не меняет SQLite path, target
logs или observability paths из stand config.

## Конфигурация

Локальный `measurement.conf` не переносим между машинами без проверки `db`.

| Параметр | Назначение | Default |
|---|---|---|
| `db` | SQLite result path | `./arduino_data.db` |
| `measurements-per-group` | Requests в группе, 1-1500 | `1500` |
| `measurement-interval-us` | Интервал requests | `300` |
| `response-timeout-us` | Deadline одного Arduino response | `10000` |
| `auto-stop-groups` | Group count, 0 без ограничения | `2500` |
| `target-board` | Board label | `unknown` |
| `target-kernel` | Kernel label | `unknown` |
| `target-stress` | `on` или `off` | `off` |
| `target-payload` | `on` или `off` | `off` |
| `prometheus-url` | Prometheus API | stand-specific |

Автоматические параметры:

```text
group_duration = measurements-per-group * measurement-interval-us
worst-count = max(1, 5% от measurements-per-group)
timeout-us = group_duration * 3
check-interval-us = group_duration
```

`timeout-us` контролирует PC fall monitoring целой группы.
`response-timeout-us` независимо ограничивает один outstanding Arduino request.
Явные `timeout-us` и `check-interval-us` заменяют auto calculation.

## Interactive Collection

```bash
rt-tester-receiver --params /path/to/measurement.conf
```

Команды receiver:

```text
start
stop
exit
```

Каждый `start` создает новую session.

## Noninteractive Collection

```bash
rt-tester-receiver \
  --params /path/to/measurement.conf \
  --groups 3 \
  --start \
  --exit-on-stop
```

Для внешней trace correlation задайте session ID:

```bash
rt-tester-receiver \
  --params /path/to/measurement.conf \
  --session-id 123456 \
  --groups 3 \
  --start \
  --exit-on-stop
```

Mode runners обычно формируют receiver config и управляют lifecycle сами.
Не запускайте второй receiver для того же serial port и session.

## Trace Import

После supervised session:

```bash
rt-tester-import-trace arduino_data.db 123456 \
  --prometheus-url http://localhost:9091

rt-tester-trace-summary arduino_data.db --session-id 123456
```

Importer заполняет `trace_group_metrics` по ключу
`session_id/group_index/host/stage`.

## Integrity

Перед анализом проверьте:

```text
requests_sent = responses_received + timeout_count
group indexes непрерывны
session ID согласован с trace data
stored latency count соответствует worst-count
```

Подробные таблицы находятся в [SQLite Schema](../reference/sqlite-schema.md).
