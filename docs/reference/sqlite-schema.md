# GPIO Session SQLite Schema

Schema создается `src/pc-receiver/database.py`. Existing DB могут содержать
legacy columns/tables после migrations; ниже описана текущая canonical schema.

## `groups`

Одна строка на Arduino group:

```text
id, session_id, group_index
pc_timestamp, pc_timestamp_us, arduino_timestamp
jitter_us, delay_us, measurements_per_group, worst_count
requests_sent, responses_received, timeout_count
target_board, target_kernel, target_stress, target_payload
created_at
```

`session_id/group_index` уникален. Integrity relation:

```text
requests_sent = responses_received + timeout_count
```

## `latencies`

Stored worst tail каждой группы:

```text
id, group_id, latency_us, rank_in_group
```

`group_id` ссылается на `groups.id` с cascade delete.

## `events`

Session lifecycle и fall/recovery events:

```text
id, session_id, event_type
event_time, event_time_us, time_since_start_us
group_index, details, created_at
```

## `soc_metrics`

Prometheus summaries на группу:

```text
id, session_id, group_index, pc_timestamp
cpu_percent, memory_percent, cpu_max, mem_max
cpu_avg, mem_avg, samples_in_group, duration_ms, created_at
```

## `trace_group_metrics`

Imported supervised trace stages:

```text
id, session_id, group_index, host, stage
count, min_us, avg_us, max_us, created_at
```

`session_id/group_index/host/stage` уникален.

## `schema_version`

```text
version, applied_at
```

Таблица зарезервирована для version tracking. Текущий код создает ее, но пока
не записывает и не проверяет номер schema автоматически.

## Primary Artifact

SQLite DB является primary source of truth для GPIO/supervised sessions.
Prometheus dashboards и generated reports являются производными представлениями.
