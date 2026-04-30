# Тестирование БВЦ АРМ

[Стенд](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend_bvc.jpg)

#### Сводная таблица результатов тестирование в пользовательском пространстве

| Условия | Количество падений | Количество выходов за порог | Худшая задержка| Avg latency в худших 5 % | Avg jitter |
| - | - | - | - | - | - |
| - | 0 | 0 | 0 | 0 | 0 |
| - | 0 | 0 | 0 | 0 | 0 |
| - | 0 | 0 | 0 | 0 | 0 |
| - | 0 | 0 | 0 | 0 | 0 |


## Схема стенда

Текущая реализация предполагает собой схему, при которой 
- БВЦ АРМ - исследуемая плата.
- Arduino Mega 2560 - инструмент тестирования;
- ПК - место сбора данных и их визуализации.

[Результаты](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/results_bcvmarm)


Схема подключения:

 - Arduino pin 7 → БВЦ_АРМ pin (/dev/gpiochip0 GPIO 0)
 - БЦВМ АРМ pin (/dev/gpiochip0 GPIO 4) →  Arduino pin 20

 Между устройствами стоит логический преобразователь уровней.

[Распиновка](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/pinout_bvс.jpg)


## Код для БВЦ АРМ

[Код для БВЦ](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/socs-investigation)

Собрать код для БВЦ:

```
gcc  -pthread -o bvc_arm-monitor main.c gpio_handler_bvc.c metrics_collector.c utils.c log_writer.c -lgpiod -lrt
```

