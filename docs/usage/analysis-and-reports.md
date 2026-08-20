# Analysis and Reports

Инструменты этого документа выполняются из source checkout. Они не входят в
RPM `rt-tester-tools` и требуют pandas, numpy и matplotlib.

Рабочий каталог:

```bash
cd src/pc-receiver
```

## Sessions И Validation

```bash
./plot_statistics.py DB --limit 250 sessions
./plot_statistics.py DB --limit 250 details SESSION
./plot_statistics.py DB validate --session SESSION
./plot_statistics.py DB latest --stress on
./plot_statistics.py DB latest --stress off
```

`--limit` является latency threshold в микросекундах: историческая методика
использует `75` для unloaded и `250` для stressed sessions. Число анализируемых
stored tail rows задает отдельный global option `--top`.

## Графики

```bash
./plot_statistics.py DB --session SESSION --limit 250 all
./plot_statistics.py DB --session SESSION --output latency.png latency+soc
./plot_statistics.py DB --session SESSION --output jitter.png jitter+soc
./plot_statistics.py DB trace --session SESSION --output trace.png
./plot_statistics.py DB events --session SESSION --output events.png
```

## Сравнение

```bash
./plot_statistics.py DB compare SESSION_A SESSION_B
./plot_statistics.py DB compare SESSION_A SESSION_B --mode latency
./plot_statistics.py DB compare SESSION_A SESSION_B --mode jitter
./plot_statistics.py DB compare SESSION_A SESSION_B --mode overlay
./plot_statistics.py DB compare SESSION_A SESSION_B --normalize
```

Сравнивайте sessions только после проверки board, kernel, handler mode,
workload, group size, interval, timeout и integrity counters.

## Полный Report

```bash
./plot_statistics.py DB report \
  --session SESSION \
  --limit 250 \
  --output-dir ./report/session_SESSION
```

Report включает overview, latency/SoC, jitter/SoC, trace, events, Markdown
summary и HTML index.

## Merge Databases

```bash
python3 merge_databases.py ../../tests merged.db
```

Merge сохраняет sessions из нескольких DB для общего comparison. Сохраните
исходные DB: merged catalog не заменяет raw experiment artifacts.
