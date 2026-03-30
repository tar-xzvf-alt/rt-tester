# Тестирование StarFive VisionFive v2

[Стенд](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend_starfive.jpg)

## Схема стенда

Текущая реализация предполагает собой схему, при которой 
- StarFive VisionFive v2 - исследуемая плата.
- Arduino Mega 2560 - инструмент тестирования;
- ПК - место сбора данных и их визуализации.

[Результаты](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/results_starfive)


Схема подключения:

 - Arduino pin 7 → Starfive pin (GPIO 60)
 - Starfive pin (GPIO 61) →  Arduino pin 20

 Между устройствами стоит логический преобразователь уровней.

[Распиновка](https://wiki.52pi.com/images/thumb/0/0c/Vf2_GPIO.jpg/800px-Vf2_GPIO.jpg)


## Код для Visionfive

[Код для Starfive](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/socs-investigation)

Собрать код для Starfive:

```
gcc  -pthread -o starfive-monitor main.c gpio_handler_starfive.c metrics_collector.c utils.c log_writer.c -lgpiod -lrt
```

