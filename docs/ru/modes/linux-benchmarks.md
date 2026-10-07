# Тесты отзывчивости Linux

[English](../../modes/linux-benchmarks.md)

Этот режим запускает уже установленный `cyclictest` на целевой плате через SSH.
Он измеряет задержку (latency) пробуждения планировщиком без Arduino, GPIO
(линий ввода-вывода общего назначения), SQLite приёмника и remote write Prometheus.
Используйте его для сравнения ядер, нагрузок, регуляторов частоты и политики
энергопотребления; он не измеряет полный физический тракт ответа GPIO.

## Подготовка

На целевой плате с ALT, если репозитории содержат эти пакеты:

```bash
apt-get install linux-rt-tests openssh-server
# For stressed runs:
apt-get install stress-ng
```

Внешний пакет `rt-handler-0.1.8-alt1` также объявляет зависимости тестов и нагрузки;
сам запуск теста не требует использования обработчика GPIO. Предварительная
проверка сценария проверяет SSH, исполняемый cyclictest, ожидаемое ядро, версию
пакета и требования нагрузки. При неудачной проверке полный комплект не создаётся.

Скопируйте и отредактируйте установленные лабораторные профили:

```text
/usr/share/rt-tester-tools/configs/stands/visionfive2-rt-cyclictest-idle.conf
/usr/share/rt-tester-tools/configs/stands/visionfive2-rt-cyclictest-stressed.conf
```

Замените частные адреса, ожидаемое ядро, корневой выходной каталог и настройки публикации.

```bash
rt-tester-run-linux-benchmark --config ./cyclictest-idle.conf --duration 10m
rt-tester-run-linux-benchmark --config ./cyclictest-stressed.conf --duration 10m
rt-tester-run-linux-benchmark --config ./cyclictest-idle.conf --print-command
rt-tester-run-linux-benchmark --config ./cyclictest-idle.conf \
  --output-root ~/.local/state/rt-tester/my-series
```

`--print-command` выводит сгенерированную команду теста. Для синтаксиса командной
строки используйте `--help`. Десятисекундная пробная проверка проверяет цепочку
сбора, а не поведение в наихудшем случае.

## Параметры и жизненный цикл

Лабораторные профили VisionFive 2 используют по одному потоку FIFO на каждый
активный CPU:

```text
--default-system --smp --policy=fifo --priority=95
--interval=1000 --distance=0 --mlockall
```

Нагрузка в нагруженном варианте:

```text
stress-ng --cpu 4 --cpu-method int64 --vm 1 --vm-bytes 70% --vm-keep --timeout 0
```

Сценарий записывает команду и состояние целевой платы, собирает исходный JSON,
гистограмму и журналы в `/tmp` платы, копирует их в локальный `.<run_uid>.partial`,
проверяет артефакты, записывает `manifest.json` и атомарно переименовывает каталог
в завершённый `<run_uid>`. Он останавливает созданную им группу процессов нагрузки
и сохраняет её журнал.

## Основной артефакт и публикация

Полный комплект включает `manifest.json`, `cyclictest.json`, `histogram.txt`,
`stdout.log`, `stderr.log`, а для нагруженного запуска — `stress.log`/`stress.pid`.
Манифест фиксирует ядро, архитектуру, регуляторы частоты, пакеты инструментов,
команду, нагрузку, число циклов, выход за диапазон гистограммы, размеры и контрольные
суммы SHA256. Сохраняйте завершённые комплекты неизменными; публикация отклоняет
изменённые или не объявленные файлы.

Читайте локальные метаданные и сводку в манифесте, а статистику потоков и гистограмму —
в исходном JSON. [Публикация cyclictest](../usage/publish-cyclictest.md) описывает
`--publish`, существующие комплекты и повторные попытки. Результаты публикуются
во внешний каталог `rt-results`, а не в Prometheus. Его панель —
`Cyclictest Scheduler Latency Prototype` (`rt-cyclictest-prototype`); если сервер
предоставляет её, пробросьте Grafana:

```bash
ssh -N -L 3002:127.0.0.1:3000 RESULTS_USER@RESULTS_HOST
```

Откройте `http://127.0.0.1:3002/d/rt-cyclictest-prototype/cyclictest-scheduler-latency-prototype`.
Переменная `run` выбирает один `run_uid`; переключайте её для сравнения сводок
по CPU или сравнивайте строки каталога. Исходный комплект остаётся основным
свидетельством. Для повторяемых контролируемых экспериментов используйте
[методику сравнений cyclictest](../methodology/cyclictest-comparisons.md).
