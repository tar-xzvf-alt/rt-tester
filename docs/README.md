# RT Tester Documentation

Документация организована по режимам измерения, пользовательским сценариям и
справочным материалам. Operational guides описывают текущий пакетный путь;
исторические результаты вынесены отдельно и не заменяют методику.

## Начало Работы

- [Getting Started](getting-started.md): выбрать режим и выполнить smoke test.
- [Dependencies](reference/dependencies.md): подготовить PC, target и сервер.
- [Runtime Paths](reference/runtime-paths.md): понять, где появляются данные.

## Режимы Измерения

- [Standalone GPIO](modes/standalone-gpio.md): Arduino и userspace/kernelspace handler.
- [Supervised Raw Ethernet](modes/supervised-raw-ethernet.md): runtime, supervisor и controller.
- [Linux Benchmarks](modes/linux-benchmarks.md): cyclictest без Arduino и GPIO.

## Сценарии Использования

- [PC Receiver](usage/receiver.md): collection и SQLite для Arduino/GPIO.
- [Analysis and Reports](usage/analysis-and-reports.md): source-only post-processing.
- [Publishing Cyclictest](usage/publish-cyclictest.md): автоматический remote import и retry queue.
- [Central Observability](observability/central.md): Prometheus remote write и Grafana.

## Методики

- [GPIO Measurements](methodology/gpio-measurements.md): воспроизводимые GPIO-серии.
- [Cyclictest Comparisons](methodology/cyclictest-comparisons.md): ABBA и fixed-frequency сравнение.

## Reference

- [Dependencies](reference/dependencies.md): packages по ролям.
- [Runtime Paths](reference/runtime-paths.md): local и remote state.
- [SQLite Schema](reference/sqlite-schema.md): GPIO/supervised session DB.

## Hardware И Target

- [Arduino Meter](hardware/arduino.md): firmware, wiring и serial protocol.
- [Target GPIO Software](hardware/target-gpio.md): userspace и kernelspace target paths.

## Результаты

- [Results Index](results/README.md): датированные отчеты и примененные профили.

## Правила Обновления

- README содержит только обзор и quick starts.
- Один режим имеет один canonical mode guide.
- Команды анализа и публикации описываются в `usage/`.
- Повторяемые условия эксперимента описываются в `methodology/`.
- Версии, пути и форматы данных описываются в `reference/`.
- Численные результаты и локальные артефакты описываются в `results/`.
