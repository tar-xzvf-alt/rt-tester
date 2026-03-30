# Тестирование БЦВМ АРМ

[Стенд](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend_bcvm.jpg)

## Схема стенда

Текущая реализация предполагает собой схему, при которой 
- БЦВМ АРМ - исследуемая плата.
- Arduino Mega 2560 - инструмент тестирования;
- ПК - место сбора данных и их визуализации.

[Результаты](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/results_bcvmarm)


Схема подключения:

 - Arduino pin 7 → БЦВМ_АРМ pin (/dev/gpiochip1 GPIO 9)
 - БЦВМ АРМ pin (/dev/gpiochip1 GPIO 9) →  Arduino pin 20

 Между устройствами стоит логический преобразователь уровней.

[Распиновка](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend_bcvm.jpg)


## Код для БЦВМ АРМ

[Код для Starfive](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/socs-investigation)

Собрать код для Starfive:

```
gcc  -pthread -o bcvm_arm-monitor main.c gpio_handler_bcvm.c metrics_collector.c utils.c log_writer.c -lgpiod -lrt
```

