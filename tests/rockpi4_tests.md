# Тестирование RockPI 4A 

[Стенд](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend_rockpi4.jpg)

#### Сводная таблица результатов тестирование в пользовательском пространстве

| Условия | Количество падений | Количество выходов за порог | Худшая задержка| Avg latency в худших 5 % | Avg jitter |
|------|-|---|---|---|---|
| 6.12 | 0 | 0 | 0 | 0 | 0|
| 6.12+stress| 0 | 0 |0| 0 | 0 |
| 6.12-rt | 0 | 0 |0| 0 | 0 |
| 6.12-rt+stress| 0 | 0 |0| 0 | 0 |

## Схема стенда

Текущая реализация предполагает собой схему, при которой 
- Radxa RockPI 4A - исследуемая плата.
- Arduino Mega 2560 - инструмент тестирования;
- ПК - место сбора данных и их визуализации.

[Результаты](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/results_rockpi4)


Схема подключения:

 - Arduino pin 7 → RockPI 4A pin GPIO4_A6
 - RockPI 4A pin GPIO4_A7 →  Arduino pin 20

 Между устройствами стоит логический преобразователь уровней.

[Распиновка](https://osoyoo.com/2022/07/20/rock-pi-4-gpio-control/)


## Код для RockPI4

[Код для RockPI4](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/socs-investigation)

Собрать код для RockPI4:

```
make BOARD=rockpi4
```

