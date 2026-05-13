# Тестирование БВЦ АРМ

[Стенд](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend_bvc.jpg)

#### Сводная таблица результатов тестирование в пользовательском пространстве

| Условия | Количество падений | Количество выходов за порог | Худшая задержка| Avg latency в худших 5 % | Avg jitter |
| - | - | - | - | - | - |
| 5.10.210-elbrus-def | 0 | 30 | 600 | 136.2 | 39.7 |
| 5.10.238-elbrus-def+stress | 0 | 27 | 600 | 118.1 | 33.2 |
| 5.10.238-rt | 0 | 0 | 100 | 37.5 | 2.9 |
| 5.10.238-rt+stress | 0 | 0 | 150 | 44.4 | 3.6 |


## Схема стенда

Текущая реализация предполагает собой схему, при которой 
- БВЦ АРМ - исследуемая плата.
- Arduino Mega 2560 - инструмент тестирования;
- ПК - место сбора данных и их визуализации.

[Результаты](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/results_bvcarm)


Схема подключения:

 - Arduino pin 7 → БВЦ_АРМ pin (/dev/gpiochip0 GPIO 0)
 - БЦВМ АРМ pin (/dev/gpiochip0 GPIO 4) →  Arduino pin 20

 Между устройствами стоит логический преобразователь уровней.

**Распиновка**: 

9 пин интерфейса X11- земля, 7 пин - GPI0, 8 пин - GPO0. GPI0 сопоставляется gpiochip0 линия 0, а GPO0 сопоставлен gpiochip0 линия 4.


## Код для БВЦ АРМ

[Код для БВЦ](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/socs-investigation)

Собрать код для БВЦ:

```
make BOARD=bvc_arm
```

