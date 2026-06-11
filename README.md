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

## Ссылки на код

- [Код для ПК](src/pc-receiver)
- [Код для Arduino](src/arduino-meter)
- [Код на одноплатнике (SoC)](https://altlinux.space/besogon1238/rt-handler)
- [rt-supervisor (Ethernet round-trip testing)](https://altlinux.space/besogon1238/rt-supervisor)

## Пример конфигурационного файла

[measurement.conf](src/pc-receiver/measurement.conf)
