# Тестирование RepkaPI4

[Стенд](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend_repkapi4.jpg)

#### Сводная таблица результатов тестирование в пользовательском пространстве

| Условия | Количество падений | Количество выходов за порог | Худшая задержка| Avg latency в худших 5 % | Avg jitter |
|------|-|---|---|---|---|
| 6.12 | 0 | 0 | 0 | 0 | 0|
| 6.12+stress| 0 | 0 |0| 0 | 0 |
| 6.12-rt | 0 | 0 |0| 0 | 0 |
| 6.12-rt+stress| 0 | 0 |0| 0 | 0 |

## Схема стенда

Текущая реализация предполагает собой схему, при которой 
- RepkaPI4- исследуемая плата.
- Arduino Mega 2560 - инструмент тестирования;
- ПК - место сбора данных и их визуализации.

[Результаты](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/results_repkapi4)


Схема подключения:

 - Arduino pin 7 → RepkaPI4 pin PG13
 - RepkaPI4 pin PG12 →  Arduino pin 20

 Между устройствами стоит логический преобразователь уровней.

[Распиновка](https://repka-pi.ru/docs/15)


## Код для RepkaPI4

[Код для RepkaPI4](https://altlinux.space/besogon1238/rt-handler)

Собрать код для RepkaPI4:

```
make BOARD=repkapi4
```
