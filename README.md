# Тестирование различных плат

Проект для измерения real-time задержек между Arduino Mega и одноплатниками.

## Результаты тестирования

| Платформа | Документация |
|-----------|-------------|
| Lichee RV Dock | [lichee_tests.md](tests/lichee_tests.md) |
| Radxa RK3588 5b | [radxa_tests.md](tests/radxa_tests.md) |
| Starfive Visionfive 2 | [visionfive_tests.md](tests/visionfive_tests.md) |
| БЦВМ АРМ | [bcvmarm_tests.md](tests/bcvmarm_tests.md) |
| БВЦ АРМ | [bvcarm_tests.md](tests/bvcarm_tests.md) |
| RepkaPI4 | [repkapi4_tests.md](tests/repkapi4_tests.md) |
| RockPI4 | [rockpi4_tests.md](tests/rockpi4_tests.md) |
| MangoPI | [mangopi_tests.md](tests/mangopi_tests.md) |

**Сводные таблицы результатов можно найти по ссылкам выше.**

## Документация по компонентам

| Компонент | Файл |
|-----------|------|
| ПК (receiver, trace import/summary, source-only анализ БД) | [docs/receiver.md](docs/receiver.md) |
| Arduino (прошивка, параметры, JSON формат) | [docs/arduino.md](docs/arduino.md) |
| Одноплатник/SoC (`rt-handler`, GPIO, controller-emu) | [docs/soc.md](docs/soc.md) |
| Standalone GPIO режим (`rt-handler` + receiver) | [docs/standalone-gpio.md](docs/standalone-gpio.md) |
| Stand pipeline, Prometheus + Grafana + зависимости | [docs/prometheus.md](docs/prometheus.md) |
| Методика испытаний | [docs/methodology.md](docs/methodology.md) |

## Запуск Из Пакета

Пакет `rt-tester-tools` запускается из любого каталога только через wrappers в
`/usr/bin`; пакетные конфиги нужно указывать полным путем из
`/usr/share/rt-tester-tools`:

```bash
rt-tester-run-gpio \
    --config /usr/share/rt-tester-tools/configs/stands/visionfive2-standalone-gpio.conf

rt-tester-run-stand \
    --config /usr/share/rt-tester-tools/configs/stands/rockpi-plc-visionfive2-controller.conf
```

Также устанавливаются команды `rt-tester-receiver`, `rt-tester-import-trace` и
`rt-tester-trace-summary`. Переменная `RT_TESTER_ROOT` предназначена для
тестирования wrappers с другим data root; при обычной установке она не нужна.

## Состав Пакета

RPM содержит:

- пять wrappers `/usr/bin/rt-tester-*`;
- два runner-а, receiver, import/summary trace-утилиты и необходимые им Python-модули в `/usr/share/rt-tester-tools`;
- пять stand config из `configs/stands/`;
- Grafana dashboards и provisioning для двух режимов;
- `prometheus/trace-prometheus-local-tunnel.yml`;
- `README.md`, `LICENSE.md` и `docs/*.md` как документацию RPM.

В RPM намеренно не входят Arduino firmware, тестовые результаты и БД, source
trees `rt-handler`/`rt-supervisor`/`rt-controller`, а также source-only утилиты
`plot_statistics.py`, `merge_databases.py`, `soc_monitor.py` и
`promql_metrics.py`. Не входят и альтернативные файлы
`prometheus/prometheus.yml`, `prometheus/trace-prometheus.yml` и legacy
`grafana/rt-tester-dashboard.json`. Упоминания этих файлов в установленной
документации описывают работу из checkout, а не содержимое RPM.

## Пути Runtime-Данных

- SQLite БД из пакетных stand config находятся в `/tmp/rt-tester-*.db`.
- Локальные pid/log/data/config Prometheus и Grafana находятся в `/tmp`.
- Target logs, traces и pid-файлы из stand config находятся в `/tmp` на соответствующей плате.
- Только внутренние логи и `metrics_all_groups.log` receiver хранятся в `${XDG_STATE_HOME:-$HOME/.local/state}/rt-tester`.
- `RT_TESTER_STATE_DIR` полностью переопределяет state directory только для receiver; runner БД, observability и target paths он не меняет.

`/tmp` не является постоянным хранилищем. Нужные БД и логи следует перенести до
перезагрузки или задать другие пути в собственной копии конфига.

## Standalone GPIO Запуск

Standalone GPIO стенд использует `rt-handler` как единственный source of truth
для C-кода на плате. Arduino напрямую подает GPIO pulse на тестируемую плату,
`rt-handler` сразу отвечает на выходной GPIO, а `receiver.py` сохраняет latency
в SQLite:

```bash
rt-tester-run-gpio \
    --config /usr/share/rt-tester-tools/configs/stands/visionfive2-standalone-gpio.conf
```

Метрики CPU/памяти собираются через `node_exporter`; логовый формат
`/var/log/soc_metrics.log` считается legacy и новым runner-ом не импортируется.
Grafana для этого режима открывается на `http://127.0.0.1:3002/d/rt-standalone-gpio`.
Подробнее: [docs/standalone-gpio.md](docs/standalone-gpio.md).

## Supervised Raw-Ethernet Запуск

Raw-Ethernet стенд описывается одним config file: runtime/supervisor board,
controller board, remote paths, transport settings, measurement parameters and
observability paths. Текущий пример конфигурации:

```bash
rt-tester-run-stand \
    --config /usr/share/rt-tester-tools/configs/stands/rockpi-plc-visionfive2-controller.conf
```

Скрипт проверяет сеть и preflight, запускает процессы на платах, receiver,
локальные Prometheus и Grafana, сохраняет SQLite БД и печатает ссылку на
дашборд с текущим `session_id`. Подробнее: [docs/prometheus.md](docs/prometheus.md).

Обычный вывод ориентирован на тестировщика: он показывает этапы запуска, ссылку
Grafana до начала длительного измерения, прогресс каждой группы и итог проверки.
Команды SSH и полный вывод foreground-процессов доступны отдельно:

```bash
rt-tester-run-stand \
    --config /usr/share/rt-tester-tools/configs/stands/rockpi-plc-visionfive2-controller.conf \
    --verbose
```

При ошибке краткий режим всё равно печатает завершившуюся команду, код возврата
и полезный хвост дочернего вывода. Background services и target-процессы всегда
пишут в log paths из выбранного stand config.

## Возможности Развертывания

| Режим | Установленные target-пакеты | Заранее размещенный source tree | Автоматический deploy | Build перед запуском |
|-------|-----------------------------|--------------------------------|----------------------|----------------------|
| Supervised | Да, штатный пакетный путь | Опционально, вручную | Нет опции `--deploy` | `--build`, только после ручного размещения source и изменения `repo`, `build` и `binary` в копии конфига |
| Standalone GPIO | Да, штатный пакетный путь | Опционально | `--deploy` из `rt-handler-local` в `repo` | `--build` собирает уже размещенный `repo`; можно сочетать с `--deploy` |

Пакетные supervised config указывают `/usr/share/rt-supervisor`,
`/usr/share/rt-controller` и установленные binaries. Они не содержат параметра
`build` и не предназначены для `--build` без изменений. Supervised runner не
копирует исходники: их нужно вручную разместить на обеих платах и настроить
собственную копию config.

Стандартный package-only config использует demo `/usr/bin/runtime`, который
устанавливается отдельным target-пакетом `rt-supervisor-runtime-example` точной
версии основного `rt-supervisor`. Для production PLC этот subpackage не нужен:
в собственной копии config задается путь к внешнему runtime wrapper.

При запуске из checkout вместо wrappers допустимы
`scripts/run_stand_measurement.py` и `scripts/run_gpio_measurement.py` с
относительными путями проекта.

## Зависимости На ALT Linux

Сборка noarch RPM:

```bash
gear-hsh --no-sisyphus-check -v --nprocs=12 /home/taranev/hasher/x86_64_chroot/
```

Запуск установленного cyclictest runner:

```bash
rt-tester-run-linux-benchmark \
  --config /usr/share/rt-tester-tools/configs/stands/visionfive2-rt-cyclictest-idle.conf
```

На target требуется штатный пакет `linux-rt-tests`; stressed profile также
использует `stress-ng`.

Уровни зависимостей:

- Обязательные зависимости RPM: `python3`, `python3-module-serial`, `python3-module-requests`, `/bin/sh`, `openssh-clients`, `rsync`, `coreutils`.
- Runtime ПК для полного observability: `prometheus`, опционально `grafana`; `python3-module-prometheus_client` не требуется текущему встроенному metrics server.
- Source-only анализ и графики: `python3-module-pandas`, `python3-module-numpy`, `python3-module-matplotlib`; `python3-module-paramiko` нужен только legacy SSH tooling, отсутствующему в RPM.
- Target runtime: `rt-handler` для standalone; `rt-supervisor`, `rt-controller` и `rt-supervisor-runtime-example` для стандартного supervised demo. Production PLC заменяет example своим wrapper. `prometheus-node_exporter` устанавливается для target metrics; `stress-ng` нужен только для stress config.
- Target source build: компилятор, build system и devel-пакеты соответствующего target-проекта; для `rt-handler` это `gcc make glibc-devel libgpiod-devel pkg-config`.
- Arduino firmware build: `arduino-core avr-gcc`; firmware в `rt-tester-tools` не входит.

Полный PC-набор для запуска стенда и source-only анализа:

```bash
apt-get install python3 python3-module-serial python3-module-requests \
    python3-module-pandas python3-module-numpy python3-module-matplotlib \
    python3-module-paramiko prometheus grafana openssh-clients rsync
```

Одноплатник для пакетного standalone GPIO:

```bash
apt-get install rt-handler prometheus-node_exporter stress-ng openssh-server
```

Для standalone `--deploy` дополнительно нужен локальный source tree `rt-handler`
по пути `rt-handler-local`; для `--build` source должен находиться в target
`repo`, а `binary` и `workdir` должны указывать на результат сборки.

Arduino Mega firmware:

```bash
apt-get install arduino-core avr-gcc
```

Для raw-Ethernet supervisor/controller стенда см. пакетные наборы в
`../rt-supervisor/docs/altlinux-packages.md`.

## Ссылки на код

- [Код для ПК](src/pc-receiver)
- [Код для Arduino](src/arduino-meter)
- [Код на одноплатнике (SoC)](https://altlinux.space/besogon1238/rt-handler)
- [rt-supervisor (Ethernet round-trip testing)](https://altlinux.space/besogon1238/rt-supervisor)
- [rt-controller (GPIO/controller side)](https://altlinux.space/besogon1238/rt-controller)

## Пример конфигурационного файла

[measurement.conf](src/pc-receiver/measurement.conf)
