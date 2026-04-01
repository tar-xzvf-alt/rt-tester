# Тестирование StarFive VisionFive v2

[Стенд](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend_starfive.jpg)

#### Сводная таблица результатов тестирование в пользовательском пространстве

| Условия | Количество падений | Количество выходов за порог | Худшая задержка| Avg latency в худших 5 % | Avg jitter |
|------|-|---|---|---|---|
| 6.18 | 0 | 5033 | 350 | 164.7 | 25.8|
| 6.18+stress| 0 | 71240 |600| 185.4 | 36.6 |
| 6.18-rt | 0 | 3469 |310| 172.2 | 27.4 |
| 6.18-rt+stress| 0 | 42934 |520| 149.0 | 26.1 |

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

