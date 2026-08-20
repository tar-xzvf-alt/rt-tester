# Target GPIO Software

Standalone GPIO target имеет два execution modes. Userspace source of truth
находится в [`rt-handler`](https://altlinux.space/besogon1238/rt-handler), а
kernelspace mode использует `rt_gpio_responder` из `rt-handler-kernel`.
Локальной копии target C-кода в `rt-tester` нет.

Оба handler mode реализуют ответную логику на импульсы Arduino. Метрики
CPU/памяти собираются через `node_exporter`; текстовый metrics log userspace
handler считается legacy и не используется runner-ом.

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

## Userspace Package

```bash
apt-get install rt-handler prometheus-node_exporter openssh-server
```

Board выбирается через `rt-handler -b starfive` или service config.

## Userspace Source Build

Зависимости на ALT Linux:

```bash
apt-get install gcc make glibc-devel libgpiod-devel pkg-config \
    prometheus-node_exporter stress-ng openssh-server
```

```bash
git clone https://altlinux.space/besogon1238/rt-handler.git
cd rt-handler/src
make
```

Конфигурация GPIO для каждой платы хранится в `/etc/rt-handler/boards.d/*.conf`
и во встроенных profiles `rt-handler`.
Для VisionFive 2 текущий profile в `rt-handler` называется `starfive`.

## Kernelspace Mode

Kernelspace stand config использует `execution-mode = kernelspace` и module
`rt_gpio_responder`. Runner загружает module, проверяет IRQ и не выполняет
userspace `--deploy`/`--build`. Module должен соответствовать running kernel.

Source и полная инструкция:

- [rt-handler-kernel](https://altlinux.space/besogon1238/rt-handler-kernel);
- `kernel/rt-handler/README.md` внутри repository.

Для Linux 6.18 пакет называется
`kernel-modules-rt-gpio-responder-6.18`. После установки проверьте:

```bash
uname -r
modinfo rt_gpio_responder
modprobe rt_gpio_responder board=starfive log_events=0
```

`vermagic` из `modinfo` должен соответствовать running kernel. Перед measurement
выгрузите module или остановите userspace service: одновременно GPIO lines может
владеть только один handler.

Подробный lifecycle находится в [Standalone GPIO](../modes/standalone-gpio.md).

## Утилиты для тестирования

```
chrt -f -p value pid    # изменить приоритет процесса pid на value
ps -eLo pid,cls,rtprio,cmd | grep SoC   # узнать текущий приоритет процесса/прерывания
stress-ng --cpu $(nproc) --vm $(nproc) --vm-bytes 100% &   # нагрузка на CPU и память
```
