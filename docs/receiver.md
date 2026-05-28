# Код для ПК (receiver, plot_statistics, merge_databases)

[Код для ПК](../src/pc-receiver)

Код на Python управляет измерениями задержек между Arduino Mega и одноплатником. Подключается к Arduino через последовательный порт, отправляет команды управления и принимает обработанные данные в формате JSON. Программа работает в интерактивном режиме с консольным управлением. Метрики CPU/памяти собираются через Prometheus (node_exporter) и сохраняются в SQLite базу.

После запуска код автоматически ищет подключенную Arduino Mega по доступным COM-портам или запрашивает порт вручную. Установив соединение, программа переходит в режим командной строки, где пользователь может управлять измерениями: запускать сбор данных, останавливать сбор и проверять статус.

## Конфигурационный файл

[Пример конфигурационного файла](../src/pc-receiver/measurement.conf)

| Параметр | Описание | Значение по умолчанию |
|----------|----------|---------------------|
| `db` | Путь к файлу базы данных SQLite | `./arduino_data.db` |
| `measurements-per-group` | Количество измерений в группе (200-1500) | `1500` |
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

# Автоматическое именование файла: sessionid_board_kernel_interval_worstcount_avg_latency_stress.png
./plot_statistics.py arduino_data.db all --session 123456

# Сравнение латентности и джиттера между двумя сессиями (реальные µs)
./plot_statistics.py arduino.db compare 228465 362956

# Только латентность, только джиттер или наложение на одном графике
./plot_statistics.py arduino.db compare 228465 362956 --mode latency
./plot_statistics.py arduino.db compare 228465 362956 --mode jitter --output jitter_only.png
./plot_statistics.py arduino.db compare 228465 362956 --mode overlay  # оба на одном графике
```

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
