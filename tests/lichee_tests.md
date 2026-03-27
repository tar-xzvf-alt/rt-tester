# Тестирование Lichee RV Dock 

[Стенд](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend.jpg)

## Схема стенда

Текущая реализация предполагает собой схему, при которой 
- Lichee RV Dock - исследуемая плата.
- Arduino Mega 2560 - инструмент тестирования;
- ПК - место сбора данных и их визуализации.

[Результаты](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/results_lichee)


Схема подключения:

 - Arduino pin 7 → Lichee pin PE15(GPIO 143)
 - Lichee pin PE12(GPIO 140) →  Arduino pin 20

 Между устройствами стоит логический преобразователь уровней.

[Распиновка](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/pinout.png)


## Код для Lichee

[Код для Lichee](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/socs-investigation)

Собрать код для Lichee:

```
gcc  -pthread -o radxa-monitor main.c gpio_handler_lichee.c metrics_collector.c utils.c log_writer.c -lgpiod -lrt
```

