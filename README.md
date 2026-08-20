# RT Tester

`rt-tester` измеряет latency Linux/RT-систем в трех независимых режимах:

- standalone GPIO: Arduino измеряет ответ userspace или kernelspace handler;
- supervised raw Ethernet: полный путь runtime, supervisor и controller;
- Linux benchmarks: `cyclictest` запускается на target напрямую по SSH.

Пакет `rt-tester-tools` устанавливается на управляющий ПК. Target-side
компоненты, Arduino firmware, центральная Grafana и база результатов
устанавливаются отдельно.

## Быстрый Старт

Установленный RPM предоставляет основные команды:

```text
rt-tester-run-gpio
rt-tester-run-stand
rt-tester-run-linux-benchmark
rt-tester-publish-cyclictest
rt-tester-receiver
rt-tester-import-trace
rt-tester-trace-summary
```

Standalone GPIO smoke:

```bash
rt-tester-run-gpio \
  --config /usr/share/rt-tester-tools/configs/stands/visionfive2-standalone-gpio.conf \
  --groups 3 \
  --no-prometheus \
  --no-grafana
```

Supervised raw-Ethernet smoke:

```bash
rt-tester-run-stand \
  --config /usr/share/rt-tester-tools/configs/stands/rockpi-plc-visionfive2-controller.conf \
  --groups 3 \
  --no-prometheus \
  --no-grafana
```

Cyclictest с автоматической публикацией результата:

```bash
rt-tester-run-linux-benchmark \
  --config /usr/share/rt-tester-tools/configs/stands/visionfive2-rt-cyclictest-idle.conf \
  --duration 10m \
  --publish
```

Эти smoke commands отключают central observability. Пакетные профили являются
примерами конкретных стендов. Перед новым
экспериментом скопируйте профиль и проверьте адреса, kernel version, GPIO,
пути результатов, параметры нагрузки и настройки публикации.

## Документация

Начните с [индекса документации](docs/README.md) или выберите режим:

| Задача | Документ |
|---|---|
| Первый запуск и выбор режима | [Getting Started](docs/getting-started.md) |
| Standalone userspace/kernelspace GPIO | [Standalone GPIO](docs/modes/standalone-gpio.md) |
| Полный runtime/raw-Ethernet путь | [Supervised Raw Ethernet](docs/modes/supervised-raw-ethernet.md) |
| Idle/stressed cyclictest | [Linux Benchmarks](docs/modes/linux-benchmarks.md) |
| Автоматическая отправка cyclictest | [Publishing Cyclictest](docs/usage/publish-cyclictest.md) |
| Сравнение при фиксированной частоте | [Cyclictest Methodology](docs/methodology/cyclictest-comparisons.md) |
| Receiver и SQLite collection | [PC Receiver](docs/usage/receiver.md) |
| Post-processing и reports | [Analysis and Reports](docs/usage/analysis-and-reports.md) |
| Центральные Prometheus и Grafana | [Central Observability](docs/observability/central.md) |
| Зависимости по ролям | [Dependencies](docs/reference/dependencies.md) |
| Runtime-файлы и результаты | [Runtime Paths](docs/reference/runtime-paths.md) |
| SQLite schema | [SQLite Schema](docs/reference/sqlite-schema.md) |
| Исторические отчеты | [Results Index](docs/results/README.md) |

## Архитектура Репозиториев

`rt-tester` содержит PC-side orchestration, receiver, stand profiles,
observability assets и документацию. Target-side source of truth находится в
отдельных проектах:

- [rt-handler](https://altlinux.space/besogon1238/rt-handler): standalone userspace GPIO;
- `rt-handler-kernel`: standalone kernel module;
- `rt-supervisor`: supervisor и runtime;
- `rt-controller`: controller-side bridge;
- `rt-results`: validated import, SQLite catalogs и Grafana dashboards.

## Установка

Собрать PC-side RPM:

```bash
gear-hsh --no-sisyphus-check=changelog,packager,gpg \
  --apt-config=/home/taranev/hasher/aptbox/etc/apt/apt.conf \
  --workdir=/home/taranev/hasher/rt-tester
```

Полный список зависимостей и target-пакетов приведен в
[docs/reference/dependencies.md](docs/reference/dependencies.md).

## Лицензия

Проект распространяется по GNU GPL v3. Полный текст находится в
[LICENSE.md](LICENSE.md).
