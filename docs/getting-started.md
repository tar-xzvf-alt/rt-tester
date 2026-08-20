# Getting Started

## 1. Выберите Режим

| Режим | Что измеряется | Arduino | Основная команда |
|---|---|---:|---|
| Standalone GPIO | GPIO request/response handler | Да | `rt-tester-run-gpio` |
| Supervised raw Ethernet | Полный runtime/supervisor/controller путь | Да | `rt-tester-run-stand` |
| Linux benchmark | Scheduler wake-up latency | Нет | `rt-tester-run-linux-benchmark` |

## 2. Подготовьте Роли

Управляющий ПК выполняет runners и хранит первичные результаты. Target должен
иметь SSH-доступ и компоненты выбранного режима. Arduino требуется только для
GPIO-режимов. Центральный сервер нужен только для observability или публикации,
но текущие packaged GPIO profiles настроены на project server `wetgrape.su`.
Без доступа к нему добавьте `--no-prometheus --no-grafana` или используйте
собственный local-only profile.

Подробная матрица пакетов находится в [Dependencies](reference/dependencies.md).

## 3. Проверьте Профиль

Не запускайте пакетный профиль вслепую. Проверьте:

- `[target] host`, kernel и board label;
- GPIO или raw-Ethernet topology;
- duration, group count и workload;
- output/database path;
- `[publish]` host, account, key и remote database.

Для лабораторного варианта сохраните копию профиля вне `/usr/share` и передайте
ее через `--config`.

## 4. Выполните Smoke Test

Standalone:

```bash
rt-tester-run-gpio --config /path/to/standalone.conf
```

Supervised:

```bash
rt-tester-run-stand --config /path/to/supervised.conf
```

Cyclictest без публикации:

```bash
rt-tester-run-linux-benchmark \
  --config /path/to/cyclictest.conf \
  --duration 10
```

Сначала подтвердите целостность короткого запуска, затем увеличивайте duration
или число групп. Для cyclictest runner печатает finalized bundle path. Для
Arduino/GPIO primary source of truth является SQLite session DB.

## 5. Выберите Следующий Сценарий

- GPIO: [Standalone GPIO](modes/standalone-gpio.md) или [Supervised Raw Ethernet](modes/supervised-raw-ethernet.md).
- Cyclictest: [Linux Benchmarks](modes/linux-benchmarks.md), затем [Publishing](usage/publish-cyclictest.md).
- Сравнение режимов: используйте соответствующий документ в `methodology/`.
