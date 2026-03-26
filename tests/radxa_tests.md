# Тестирование Radxa rk3588 5b

[Стенд](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend_radxa.jpg)

## Схема стенда

Текущая реализация предполагает собой схему, при которой 
- Radxa rk3588 5b - исследуемая плата.
- Arduino Mega 2560 - инструмент тестирования;
- ПК - место сбора данных и их визуализации.

[Результаты](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/results_)


Схема подключения:

 - Arduino pin 7 → Radxa pin PE16(GPIO3_B2 aka pin #138 aka gpiochip3 line 10)
 - Radxa pin PE12(GPIO3_B3 aka pin #139 gpiochip3 line 11) →  Arduino pin 20

 Между устройствами стоит логический преобразователь уровней.

[Распиновка](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/rock5bp_40pin_power_3.png)

## Код для Radxa

[Код для Radxa](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/socs-investigation)

Собрать код для Radxa:

```
gcc  -pthread -o radxa-monitor main.c gpio_handler_radxa.c metrics_collector.c utils.c log_writer.c -lgpiod -lrt
```
    