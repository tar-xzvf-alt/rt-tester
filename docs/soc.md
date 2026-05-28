# Код на одноплатнике (SoC)

Код на C работает на тестируемой плате (Radxa/Lichee/Raspberry Pi) и реализует:
- Ответную логику на импульсы от Arduino
- Сбор метрик загрузки CPU и памяти
- Логирование статистики в файл

## Архитектура программы

- `gpio_handler_thread` — обработчик GPIO-событий (реагирует на фронты от Arduino)
- Для Ethernet round-trip тестирования используется `controller-emu` из проекта [rt-supervisor](https://altlinux.space/besogon1238/rt-supervisor) (ветка `polygon`)

## Конфигурация GPIO (различается для разных плат)

| Платформа | GPIO Chip | Вход (от Arduino) | Выход (ответ) |
|-----------|-----------|-------------------|---------------|
| Radxa RK3588 | `/dev/gpiochip3` | BANK=1, LINE=2 | BANK=1, LINE=3 |
| Lichee RV Dock | `/dev/gpiochip0` | BANK=4, LINE=12 | BANK=4, LINE=16 |
| Visionfive Starfive v2 | `/dev/gpiochip0` | LINE=60 | LINE=61 |
| БЦВМ АРМ | `/dev/gpiochip0` | LINE=15 | LINE=9 |
| БВЦ АРМ | `/dev/gpiochip0` | LINE=0 | LINE=4 |
| RepkaPI4 | `/dev/gpiochip1` | BANK=6, LINE=13 | BANK=6, LINE=12 |
| MangoPI | `/dev/gpiochip0` | BANK=1, LINE=3 | BANK=1, LINE=4 |
| RockPI4 | `/dev/gpiochip4` | LINE=6 | LINE=7 |

## Сборка

```bash
make BOARD=lichee  # или radxa, repkapi4, rockpi4, ...
```

Конфигурация GPIO для каждой платы хранится в `src/socs-investigation/gpio_config.h`.

## Утилиты для тестирования

```
chrt -f -p value pid    # изменить приоритет процесса pid на value
ps -eLo pid,cls,rtprio,cmd | grep SoC   # узнать текущий приоритет процесса/прерывания
stress-ng --cpu $(nproc) --vm $(nproc) --vm-bytes 100% &   # нагрузка на CPU и память
```
