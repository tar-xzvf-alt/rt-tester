# GPIO Measurement Methodology

Standalone и supervised GPIO modes используют одинаковую Arduino measurement
model, но разные target paths. Не запускайте supervisor вручную через CMake,
если эксперимент описан packaged stand profile: lifecycle должен принадлежать
одному runner.

## Общие Условия

1. Зафиксируйте board, kernel, packages, firmware и wiring.
2. Используйте одинаковые `measurements-per-group`, interval и group count.
3. Задайте независимый `response-timeout-us` для одного Arduino response.
4. Используйте одинаковый `worst-count` или автоматические 5% группы.
5. Для stress создавайте workload только через runner и проверяйте cleanup.
6. Не смешивайте userspace/kernelspace или kernels в одной неподписанной серии.
7. Сохраняйте SQLite DB как primary artifact.

## Standalone

Используйте `rt-tester-run-gpio` и один из execution modes:

- userspace package `rt-handler`;
- userspace source deploy/build;
- kernelspace `rt_gpio_responder`.

Перед comparison выполните короткий smoke каждого mode. Для paired experiment
используйте одинаковую последовательность idle/stress и не меняйте IRQ affinity,
node_exporter priority или CPU placement между runs.

## Supervised

Используйте `rt-tester-run-stand`. Runner должен единолично управлять runtime,
supervisor, controller, Arduino readiness barrier, workload и trace collection.
После session импортируйте trace aggregates и проверьте integrity counters.

## Проверки Целостности

Для каждой группы должны согласовываться:

```text
requests_sent = responses_received + timeout_count
histogram/tail sample count соответствует profile
session ID совпадает между Arduino, SQLite и trace data
```

Network drops, softnet drops, sequence anomalies и missing responses должны
быть объяснены до статистического сравнения.

## Анализ

Для unloaded sessions историческая методика использует latency threshold
`--limit 75`, для stressed sessions `--limit 250`. Число анализируемых stored
tail rows задается через `--top`; ни один из этих параметров не является Arduino
response deadline.

Сравнивайте mean, p95/p99 stored tail, maximum, RMS jitter и integrity metrics.
Один maximum не является достаточным основанием для вывода.
