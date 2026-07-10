# Тестирование БЦВМ АРМ

[Стенд](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend_bcvm.jpg)

## Сводная таблица результатов

#### Сводная таблица результатов тестирование в пользовательском пространстве

| Условия | Количество падений | Количество выходов за порог | Худшая задержка| Avg latency в худших 5 % | Avg jitter |
|------|-|---|---|---|---|
| 6.12.71 | 0 | 3 | 270 | 25.3 | 2.2|
| 6.12.71+stress| 0 | 72 |300| 73.2 | 13.0 |
| 6.18.20-rt | 0 | 0 |75| 23.6 | 2.1 |
| 6.18.20-rt+stress| 0 | 32 |260| 50.6 | 7.4 |

## Схема стенда

Текущая реализация предполагает собой схему, при которой 
- БЦВМ АРМ - исследуемая плата.
- Arduino Mega 2560 - инструмент тестирования;
- ПК - место сбора данных и их визуализации.

[Результаты](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/results_bcvmarm)


Схема подключения:

 - Arduino pin 7 → БЦВМ_АРМ pin (/dev/gpiochip1 GPIO 9)
 - БЦВМ АРМ pin (/dev/gpiochip1 GPIO 9) →  Arduino pin 20
 - БЦВМ GND → Arduino GND
 - Arduino 3.3 V → Arduino 5 V через преобразователь!

 Между устройствами стоит логический преобразователь уровней.

[Распиновка](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/pinout_bcvm.jpg)


## Код для БЦВМ АРМ

[Код для БЦВМ](https://altlinux.space/besogon1238/rt-handler)

Собрать код для Starfive:

```
make BOARD=bcvm
```
