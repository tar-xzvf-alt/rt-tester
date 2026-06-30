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
| ПК (receiver, plot_statistics, merge, конфигурация, БД) | [docs/receiver.md](docs/receiver.md) |
| Arduino (прошивка, параметры, JSON формат) | [docs/arduino.md](docs/arduino.md) |
| Одноплатник/SoC (GPIO-таблица, сборка, controller-emu) | [docs/soc.md](docs/soc.md) |
| Prometheus + Grafana + зависимости | [docs/prometheus.md](docs/prometheus.md) |
| Методика испытаний | [docs/methodology.md](docs/methodology.md) |

## Стандартный запуск стенда

Для стенда, где `rockpi` запускает Beremiz + `alt-rt-supervisor`, а
`visionfive2` запускает GPIO/controller side:

```bash
scripts/run_stand_measurement.py \
    --config configs/stands/rockpi-plc-visionfive2-controller.conf
```

Скрипт проверяет сеть и preflight, запускает процессы на платах, receiver,
локальные Prometheus и Grafana, сохраняет SQLite БД и печатает ссылку на
дашборд с текущим `session_id`. Подробнее: [docs/prometheus.md](docs/prometheus.md).

## Зависимости на ALT Linux

ПК для `src/pc-receiver/receiver.py`, импорта trace-метрик и построения графиков:

```bash
apt-get install python3 python3-module-serial python3-module-requests \
    python3-module-pandas python3-module-numpy python3-module-matplotlib \
    python3-module-paramiko prometheus grafana openssh-clients rsync
```

Одноплатник для standalone SoC monitor из `src/socs-investigation/`:

```bash
apt-get install gcc make glibc-devel libgpiod-devel pkg-config \
    prometheus-node_exporter stress-ng openssh-server
```

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

## Пример конфигурационного файла

[measurement.conf](src/pc-receiver/measurement.conf)
