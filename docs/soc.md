# Код на одноплатнике (SoC)

Код на C для standalone GPIO режима находится во внешнем репозитории
[`rt-handler`](https://altlinux.space/besogon1238/rt-handler). Это единственный
source of truth для обработчика GPIO на одноплатнике; локальная копия
`src/socs-investigation/` из `rt-tester` удалена.

`rt-handler` работает на тестируемой плате и реализует ответную логику на
импульсы от Arduino. Метрики CPU/памяти в новых запусках собираются через
`node_exporter`; текстовый metrics log `rt-handler` считается legacy и не
используется runner-ом `rt-tester`.

## Архитектура программы

- `gpio_handler_thread` — обработчик GPIO-событий (реагирует на фронты от Arduino)
- Для Ethernet round-trip тестирования используется `controller-emu` из проекта [rt-controller](https://altlinux.space/besogon1238/rt-controller).

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

Зависимости на ALT Linux:

```bash
apt-get install gcc make glibc-devel libgpiod-devel pkg-config \
    prometheus-node_exporter stress-ng openssh-server
```

```bash
cd src && make
```

Board выбирается во время запуска, например `rt-handler -b starfive`, или через
пакетный service config `/etc/sysconfig/rt-handler`.
Конфигурация GPIO для каждой платы хранится в `/etc/rt-handler/boards.d/*.conf`
и во встроенных profiles `rt-handler`.
Для VisionFive 2 текущий profile в `rt-handler` называется `starfive`.

## Утилиты для тестирования

```
chrt -f -p value pid    # изменить приоритет процесса pid на value
ps -eLo pid,cls,rtprio,cmd | grep SoC   # узнать текущий приоритет процесса/прерывания
stress-ng --cpu $(nproc) --vm $(nproc) --vm-bytes 100% &   # нагрузка на CPU и память
```
