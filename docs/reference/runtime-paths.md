# Runtime Paths

| Режим | Primary result | Local state | Remote state |
|---|---|---|---|
| Standalone GPIO | SQLite session DB | receiver logs, temporary observability | target handler logs |
| Supervised | SQLite DB и trace aggregates | receiver, Prometheus/Grafana state | runtime/controller logs and traces |
| Cyclictest | finalized UUID bundle | publication sidecars | `rt-results` cyclictest catalog |

## Cyclictest

Текущие лабораторные VisionFive 2 profiles задают конкретный output root:

```text
/home/taranev/.local/state/rt-tester/cyclictest-prototype/<run_uid>/
```

Перед использованием на другой машине скопируйте profile и замените его на
пользовательский путь, например:

```text
~/.local/state/rt-tester/cyclictest-results/<run_uid>/
~/.local/state/rt-tester/cyclictest-publish/<run_uid>.json
```

Во время collection создается hidden `.<run_uid>.partial`. Complete bundle
атомарно переименовывается в `<run_uid>`. Publication staging создается на
сервере временно и удаляется после import attempt.

Central catalog:

```text
/var/lib/rt-results-prototype/cyclictest.db
```

## Arduino/GPIO

Конкретный SQLite path задается stand/measurement config. Часть smoke profiles
использует `/tmp`, а лабораторные comparison profiles используют persistent
каталоги под `~/.local/state/rt-tester`. Всегда проверяйте config вместо
предположения, что результат находится в `/tmp`.

SQLite DB является primary artifact. Prometheus предназначен для live
observability и не заменяет session DB.
