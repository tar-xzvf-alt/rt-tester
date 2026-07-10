# Тестирование Radxa rk3588 5b

[Стенд](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend_radxa.jpg)

#### Сводная таблица результатов тестирование в пользовательском пространстве

| Условия | Количество падений | Количество выходов за порог | Худшая задержка| Avg latency в худших 5 % | Avg jitter |
|------|-|---|---|---|---|
| 6.12.76 | 0 | 0 | 150 | 29.5 | 2.5|
| 6.12.76+stress| 2 | 3647 |350| 66.3 | 11.2 |
| 6.12.76-rt | 0 | 0 |125| 36.5 | 3.6 |
| 6.12.76-rt+stress| 0 | 99 |360| 39.2 | 4.0 |


## Схема стенда

Текущая реализация предполагает собой схему, при которой 
- Radxa rk3588 5b - исследуемая плата.
- Arduino Mega 2560 - инструмент тестирования;
- ПК - место сбора данных и их визуализации.

[Результаты](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/results_radxa)


Схема подключения:

 - Arduino pin 7 → Radxa pin PE16(GPIO3_B2 aka pin #138 aka gpiochip3 line 10)
 - Radxa pin PE12(GPIO3_B3 aka pin #139 gpiochip3 line 11) →  Arduino pin 20

 Между устройствами стоит логический преобразователь уровней.

[Распиновка](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/rock5bp_40pin_power_3.png)

## Код для Radxa

[Код для Radxa](https://altlinux.space/besogon1238/rt-handler)

Собрать код для Radxa:

```
make BOARD=radxa
```
