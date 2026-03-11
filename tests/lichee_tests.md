# Тестирование Lichee RV Dock 

[Стенд](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/stend.jpg)

## Схема стенда

Текущая реализация предполагает собой схему, при которой 
- Lichee RV Dock - исследуемая плата.
- Arduino Mega 2560 - инструмент тестирования;
- ПК - место сбора данных и их визуализации.

[Визуализации результатов](https://altlinux.space/besogon1238/rt-tester/src/branch/main/results)


Схема подключения:

 - Arduino pin 7 → Lichee pin PE16(GPIO 144)
 - Lichee pin PE12(GPIO 140) →  Arduino pin 20

 Между устройствами стоит логический преобразователь уровней.

[Распиновка](https://altlinux.space/besogon1238/rt-tester/src/branch/main/pictures/pinout.png)


## Код для Lichee

[Код для Lichee](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/socs-ivestigation/lichee.c)

Собрать код для Lichee:

```
gcc lichee.c -lgpiod -o lichee
```

