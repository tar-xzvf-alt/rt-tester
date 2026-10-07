# ПО GPIO целевой платы

[English](../../hardware/target-gpio.md)

GPIO — линии ввода-вывода общего назначения. Логика автономного ответа поддерживается
во внешних проектах: [rt-handler](https://altlinux.space/besogon1238/rt-handler)
для пространства пользователя и
[rt-handler-kernel](https://altlinux.space/besogon1238/rt-handler-kernel)
для модуля `rt_gpio_responder`. Этот репозиторий не дублирует целевой код на C.
Мост GPIO/raw Ethernet режима с супервизором — `controller-emu` из
[rt-controller](https://altlinux.space/besogon1238/rt-controller).

## Соответствия линий GPIO

Ниже приведены исторические справочные соответствия плат. Перед подключением
проверьте установленный внешний профиль платы и нумерацию GPIO работающего ядра.
Обозначения банка/линии зависят от целевой платы; ни одно из этих чисел не является
номером физического контакта разъёма.

| Платформа | Устройство GPIO | Вход запроса | Выход ответа |
|---|---|---|---|
| Radxa RK3588 | `/dev/gpiochip3` | BANK=1, LINE=2 | BANK=1, LINE=3 |
| Lichee RV Dock | `/dev/gpiochip0` | BANK=4, LINE=12 | BANK=4, LINE=16 |
| VisionFive 2 | `/dev/gpiochip0` | LINE=60 | LINE=61 |
| BCVM ARM | `/dev/gpiochip0` | LINE=15 | LINE=9 |
| BVC ARM | `/dev/gpiochip0` | LINE=0 | LINE=4 |
| RepkaPI4 | `/dev/gpiochip1` | BANK=6, LINE=13 | BANK=6, LINE=12 |
| MangoPI | `/dev/gpiochip0` | BANK=1, LINE=3 | BANK=1, LINE=4 |
| RockPI4 | `/dev/gpiochip4` | LINE=6 | LINE=7 |

Соответствия пространства пользователя находятся в `/etc/rt-handler/boards.d/*.conf`
и встроенных профилях. Имя платы VisionFive 2 в обработчике — `starfive`.
Arduino D7 подключается через подходящее согласование уровней к входу запроса,
выход ответа возвращается на D20, а все платы имеют общую землю. См.
[Arduino](arduino.md) и [автономное руководство](../usage/standalone-gpio-walkthrough.md).

## Установленный обработчик пространства пользователя

В ALT Linux с соответствующим репозиторием пакетов:

```bash
apt-get install rt-handler prometheus-node_exporter openssh-server
```

Выберите плату через `rt-handler -b starfive` или конфигурацию службы.
Обычно сценарий сам запускает `/usr/sbin/rt-handler`. Работающий `node_exporter`
обязателен даже без мониторинга: сценарий проверяет его, переводит в `SCHED_OTHER`
и привязывает к CPU служебных задач. Данные CPU/памяти поступают через Prometheus;
старый текстовый журнал метрик пространства пользователя не импортируется
и обычно направлен в `/dev/null`. Для каждого эксперимента фиксируйте пакет/ревизию
обработчика, ядро, профиль платы, привязку IRQ и приоритет FIFO.

## Разработка из исходников

Для сборки на целевой плате следуйте внешним инструкциям `rt-handler`.
Типичные зависимости сборки ALT — GCC, make, заголовки разработки glibc
и libgpiod, а также pkg-config; зависимости выполнения остаются отдельными.

```bash
git clone https://altlinux.space/besogon1238/rt-handler.git
cd rt-handler/src
make
```

Автономный сценарий поддерживает настроенные пути развёртывания/сборки
пространства пользователя; см. [автономный режим](../modes/standalone-gpio.md)
и [разработку и тестирование](../development/development-and-testing.md).
Не подставляйте пути сборки из исходников в профиль установленного ПО без адаптации.

## Обработчик пространства ядра

Задайте `execution-mode = kernelspace` и `module = rt_gpio_responder` в профиле
стенда. Сценарий загружает модуль и проверяет диагностику IRQ; он отклоняет
`--deploy`/`--build` пространства пользователя. Линиями GPIO может владеть только
один обработчик, поэтому перед работой модуля остановите службу пространства
пользователя, а для работы в пространстве пользователя выгрузите модуль.

Подробности сборки/установки определяет `kernel/rt-handler/README.md` внешнего
репозитория. Для Linux 6.18 имя пакета — `kernel-modules-rt-gpio-responder-6.18`.
На подготовленной целевой плате:

```bash
uname -r
modinfo rt_gpio_responder
# This changes target state; normally let the measurement runner load it:
modprobe rt_gpio_responder board=starfive log_events=0
```

Проверьте `vermagic` относительно работающего ядра и подтвердите соответствия
линий платы в модуле. Одно имя пакета не подтверждает совместимость.

## Проверка планирования

`ps -eLo pid,tid,cls,rtprio,psr,comm` показывает планирование и размещение каждого
потока по CPU. `chrt -f -p PRIORITY PID` изменяет приоритет FIFO и требует прав;
зафиксируйте выбранное значение. Не добавляйте произвольные конкурирующие нагрузки
в контролируемый запуск: используйте настройки нагрузки профиля и проверяйте очистку.
