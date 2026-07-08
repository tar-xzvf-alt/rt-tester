# Код для ПК (receiver, plot_statistics, merge_databases)

[Код для ПК](../src/pc-receiver)

Код на Python управляет измерениями задержек между Arduino Mega и одноплатником. Подключается к Arduino через последовательный порт, отправляет команды управления и принимает обработанные данные в формате JSON. Программа работает в интерактивном режиме с консольным управлением. Метрики CPU/памяти собираются через Prometheus (node_exporter) и сохраняются в SQLite базу.

## Зависимости

На ALT Linux для сбора данных, импорта trace-метрик и построения графиков:

```bash
apt-get install python3 python3-module-serial python3-module-requests \
    python3-module-pandas python3-module-numpy python3-module-matplotlib \
    python3-module-paramiko prometheus openssh-clients rsync
```

`sqlite3` используется через стандартный модуль Python. `paramiko` нужен только
для legacy SSH SoC monitor tooling; основной сбор SoC-метрик идёт через
Prometheus/node_exporter.

После запуска код автоматически ищет подключенную Arduino Mega по доступным COM-портам или запрашивает порт вручную. Установив соединение, программа переходит в режим командной строки, где пользователь может управлять измерениями: запускать сбор данных, останавливать сбор и проверять статус.

## Конфигурационный файл

[Пример конфигурационного файла](../src/pc-receiver/measurement.conf)

| Параметр | Описание | Значение по умолчанию |
|----------|----------|---------------------|
| `db` | Путь к файлу базы данных SQLite | `./arduino_data.db` |
| `measurements-per-group` | Количество измерений в группе (1-1500) | `1500` |
| `measurement-interval-us` | Интервал между измерениями (мкс) | `300` |
| `auto-stop-groups` | Автоостановка после N групп (0 = бесконечно) | `2500` |
| `target-board` | Название тестируемой платы | `unknown` |
| `target-kernel` | Версия ядра на тестируемой плате | `unknown` |
| `target-stress` | Наличие системной нагрузки на плате (`on`/`off`) | `off` |
| `target-payload` | Полезная нагрузка между импульсами (`on`/`off`) | `off` |

**Автоматически рассчитываемые параметры:**

| Параметр | Формула | Пример (1500 × 300 µs) |
|----------|---------|----------------------|
| `worst-count` | 5% от `measurements-per-group` (мин. 1) | 75 |
| `timeout-us` | `group_duration × 2` | 900,000 µs (0.9 сек) |
| `check-interval-us` | `group_duration` | 450,000 µs (0.45 сек) |

где `group_duration = measurements-per-group × measurement-interval-us`.

Если `timeout-us` или `check-interval-us` **явно указаны** в конфигурации — используются ручные значения вместо авто-расчёта.

Секция `[soc]` больше не используется — метрики CPU/памяти собираются через node_exporter.

## Сбор данных

```bash
./receiver.py --params /path/to/params.conf
# Интерактивные команды:
start # запуск сессии сбора N
stop  # остановка сессии сбора N
# повторный вызов 'start' — новая сессия
exit  # завершение сбора
```

Неинтерактивный запуск с автостартом и выходом после остановки Arduino:

```bash
./receiver.py --params /path/to/params.conf --start --exit-on-stop
```

Количество групп можно переопределить из командной строки без правки
конфигурационного файла:

```bash
./receiver.py --params /path/to/params.conf --groups 3 --start --exit-on-stop
```

Для внешней синхронизации с trace-системой можно задать session ID явно:

```bash
./receiver.py --params /path/to/params.conf --session-id 123456 --groups 3 --start --exit-on-stop
```

Trace-метрики, собранные Prometheus из `rt-supervisor` exporters, импортируются
в SQLite отдельно:

```bash
./import_trace_metrics.py arduino_data.db 123456 --prometheus-url http://localhost:9090
```

Импорт заполняет таблицу `trace_group_metrics` с ключом
`session_id/group_index/host/stage`.

Краткую сводку по сохранённой trace-сессии можно вывести так:

```bash
./trace_summary.py arduino_data.db --session-id 123456
```

Для Prometheus на ПК без маршрута в сеть `10.43.0.0/24` используйте SSH tunnels
и пример конфига `prometheus/trace-prometheus-local-tunnel.yml`. Для Prometheus,
который видит RockPI/VisionFive напрямую, используйте
`prometheus/trace-prometheus.yml`.

## Анализ данных (plot_statistics)

```bash
# Список всех сессий с информацией о плате, ядре и превышениях порога
./plot_statistics.py arduino_data.db sessions --limit 250

# Детальная информация о конкретной сессии
./plot_statistics.py arduino_data.db details 123456 --limit 250

# Комплексный график (латентность, джиттер, превышения порога, загрузка SoC)
./plot_statistics.py arduino_data.db all --session 123456 --limit 250

# График латентности с наложением загрузки SoC и гистограммой превышений
./plot_statistics.py arduino_data.db latency+soc --session 123456 --limit 250 --output plot.png

# График джиттера с наложением загрузки SoC и гистограммой превышений
./plot_statistics.py arduino_data.db jitter+soc --session 123456 --limit 250

# Только график латентности (без SoC)
./plot_statistics.py arduino_data.db latency --session 123456

# Только график джиттера (без SoC)
./plot_statistics.py arduino_data.db jitter --session 123456

# Сравнение с нормализацией по оси Y ([0,1])
./plot_statistics.py arduino.db compare 228465 362956 --normalize

# Автоматическое именование файла: sessionid_board_kernel_interval_worstcount_avg_latency_stress.png
./plot_statistics.py arduino_data.db all --session 123456

# Сравнение латентности и джиттера между двумя сессиями (реальные µs)
./plot_statistics.py arduino.db compare 228465 362956

# Только латентность, только джиттер или наложение на одном графике
./plot_statistics.py arduino.db compare 228465 362956 --mode latency
./plot_statistics.py arduino.db compare 228465 362956 --mode jitter --output jitter_only.png
./plot_statistics.py arduino.db compare 228465 362956 --mode overlay  # оба на одном графике

# Последняя сессия в базе (с фильтром по stress)
./plot_statistics.py arduino_data.db latest
./plot_statistics.py arduino_data.db latest --stress on
./plot_statistics.py arduino_data.db latest --stress off

# Проверка целостности данных сессии (авто-определение последней)
./plot_statistics.py arduino_data.db validate
./plot_statistics.py arduino_data.db validate --session 123456

# График breakdown trace-стадий (столбцы stacked)
./plot_statistics.py arduino_data.db trace --session 123456
./plot_statistics.py arduino_data.db trace --session 123456 --output trace_breakdown.png

# Временная линия событий (fall/recovery/start/stop)
./plot_statistics.py arduino_data.db events --session 123456
./plot_statistics.py arduino_data.db events --session 123456 --output events.png

# Полный отчёт по сессии (все графики + Markdown-сводка + HTML)
./plot_statistics.py arduino_data.db report --session 123456
./plot_statistics.py arduino_data.db report --session 123456 --output-dir ./report/session_123456
./plot_statistics.py arduino_data.db report  # последняя сессия
./plot_statistics.py arduino_data.db report --stress on  # последняя seссия со stress
./plot_statistics.py arduino_data.db report --limit 250 --top 125
```

Отчёт генерирует в `--output-dir`:
- `session_<id>_all.png` — комплексный график (latency, jitter, exceeds, SoC)
- `session_<id>_latency_soc.png` — latency + SoC overlay
- `session_<id>_jitter_soc.png` — jitter + SoC overlay
- `session_<id>_trace.png` — breakdown trace-стадий stacked по host
- `session_<id>_events.png` — временная линия событий
- `session_<id>_summary.md` — Markdown-сводка
- `index.html` — HTML-страница со всеми графиками

## Объединение баз данных

Скрипт `merge_databases.py` сливает все .db файлы из `tests/results_*/` в одну базу:

```bash
python3 src/pc-receiver/merge_databases.py tests/ merged.db
```

После слияния можно анализировать все сессии со всех плат одновременно:

```bash
./plot_statistics.py merged.db sessions
./plot_statistics.py merged.db compare 228465 362956  # сессии с разных плат
```

## Структура базы данных SQLite

База данных содержит следующие таблицы:

### Таблица `groups`

Хранит информацию о группах измерений:

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER | Первичный ключ |
| `session_id` | INTEGER | ID сессии |
| `group_index` | INTEGER | Номер группы |
| `pc_timestamp` | TEXT | Время получения на ПК |
| `jitter_us` | REAL | RMS джиттер (мкс) |
| `delay_us` | INTEGER | Интервал между измерениями (мкс) |
| `measurements_per_group` | INTEGER | Количество измерений в группе |
| `worst_count` | INTEGER | Количество сохраненных худших задержек |
| `target_board` | TEXT | Название тестируемой платы |
| `target_kernel` | TEXT | Версия ядра |
| `target_stress` | TEXT | Наличие нагрузки (`on`/`off`) |
| `target_payload` | TEXT | Полезная нагрузка между импульсами (`on`/`off`) |

### Таблица `latencies`

Хранит худшие задержки для каждой группы:

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER | Первичный ключ |
| `group_id` | INTEGER | Ссылка на `groups.id` |
| `latency_us` | INTEGER | Значение задержки (мкс) |
| `rank_in_group` | INTEGER | Ранг (1 = худшая) |

### Таблица `soc_metrics`

Хранит метрики загрузки одноплатника:

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER | Первичный ключ |
| `session_id` | INTEGER | ID сессии |
| `group_index` | INTEGER | Номер группы |
| `cpu_percent` | REAL | Средняя загрузка CPU (%) |
| `memory_percent` | REAL | Средняя загрузка памяти (%) |
| `cpu_max` | REAL | Максимальная загрузка CPU (%) |
| `mem_max` | REAL | Максимальная загрузка памяти (%) |
| `samples_in_group` | INTEGER | Количество измерений в группе |
| `duration_ms` | REAL | Фактическая длительность группы (мс) |

### Таблица `events`

Хранит события сессии (старт, стоп, падения, восстановления):

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER | Первичный ключ |
| `session_id` | INTEGER | ID сессии |
| `event_type` | TEXT | Тип события (`start`/`stop`/`fall`/`recovery`) |
| `event_time` | TEXT | Время события |
| `group_index` | INTEGER | Номер группы на момент события |
| `details` | TEXT | Дополнительная информация |
