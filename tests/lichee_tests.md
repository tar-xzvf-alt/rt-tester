# Тестирование Lichee RV Dock 

[Стенд](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend_lichee.jpg)

#### Сводная таблица результатов тестирование в пользовательском пространстве

| Условия | Количество падений | Количество выходов за порог | Худшая задержка| Avg latency в худших 5 % | Avg jitter |
|------|-|---|---|---|---|
| 6.12 | 0 | 45812 | 335 | 249.8 | 17.1|
| 6.12+stress| 0 | 95198 |575| 252.8 | 18.8 |
| 6.12-rt | 0 | 21684 |330| 228.4 | 13.5 |
| 6.12-rt+stress| 0 | 93643 |325| 251.4 | 16.9 |

## Схема стенда

Текущая реализация предполагает собой схему, при которой 
- Lichee RV Dock - исследуемая плата.
- Arduino Mega 2560 - инструмент тестирования;
- ПК - место сбора данных и их визуализации.

[Результаты](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/results_lichee)


Схема подключения:

 - Arduino pin 7 → Lichee pin PE15(GPIO 143)
 - Lichee pin PE16(GPIO 144) →  Arduino pin 20

 Между устройствами стоит логический преобразователь уровней.

[Распиновка](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/pinout.png)


## Код для Lichee

[Код для Lichee](https://altlinux.space/besogon1238/rt-handler)

Собрать код для Lichee:

```
make BOARD=lichee
```
