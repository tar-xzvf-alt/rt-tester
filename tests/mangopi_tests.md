# Тестирование MangoPI MQ Pro

[Стенд](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend_mangopi.jpg)

#### Сводная таблица результатов тестирование в пользовательском пространстве

| Условия | Количество падений | Количество выходов за порог | Худшая задержка| Avg latency в худших 5 % | Avg jitter |
|------|-|---|---|---|---|
| 6.12 | 0 | 0 | 0 | 0 | 0|
| 6.12+stress| 0 | 0 |0| 0 | 0 |
| 6.12-rt | 0 | 0 |0| 0 | 0 |
| 6.12-rt+stress| 0 | 0 |0| 0 | 0 |

## Схема стенда

Текущая реализация предполагает собой схему, при которой 
- MangoPI MQ PRO - исследуемая плата.
- Arduino Mega 2560 - инструмент тестирования;
- ПК - место сбора данных и их визуализации.

[Результаты](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/results_mangopi)


Схема подключения:

 - Arduino pin 7 → MangoPI pin PB3(GPIO 35)
 - MangoPI pin PB4(GPIO 36) →  Arduino pin 20

 Между устройствами стоит логический преобразователь уровней.

[Распиновка](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/pinout.png)


## Код для MangoPI

[Код для Lichee](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/socs-investigation)

Собрать код для Lichee:

```
make BOARD=mangopi
```

