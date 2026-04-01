# Тестирование БЦВМ АРМ

[Стенд](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend_bcvm.jpg)

#### Сводная таблица результатов тестирование в пользовательском пространстве

| Условия | Количество падений | Количество выходов за порог | Худшая задержка| Avg latency в худших 5 % | Avg jitter |
|------|-|---|---|---|---|
| 6.12 | 2 | 45812 | 335 | 249.8 | 17.1|
| 6.12+stress| 0 | 95198 | 252.8 | 18.8 |
| 6.12-rt | 0 | 109726 | 255.6 | 18.0 |
| 6.12-rt+stress| 0 | 45812 | 255.3 | 18.1 |


## Схема стенда

Текущая реализация предполагает собой схему, при которой 
- БЦВМ АРМ - исследуемая плата.
- Arduino Mega 2560 - инструмент тестирования;
- ПК - место сбора данных и их визуализации.

[Результаты](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/results_bcvmarm)


Схема подключения:

 - Arduino pin 7 → БЦВМ_АРМ pin (/dev/gpiochip1 GPIO 15)
 - БЦВМ АРМ pin (/dev/gpiochip1 GPIO 9) →  Arduino pin 20

 Между устройствами стоит логический преобразователь уровней.

[Распиновка](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/pinout_bcvm.jpg)


## Код для БЦВМ АРМ

[Код для БВЦ](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/socs-investigation)

Собрать код для Starfive:

```
gcc  -pthread -o bcvm_arm-monitor main.c gpio_handler_bcvm.c metrics_collector.c utils.c log_writer.c -lgpiod -lrt
```

