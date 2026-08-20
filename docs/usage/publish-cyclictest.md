# Publishing Cyclictest Results

Publisher переносит validated cyclictest bundle на central server и вызывает
remote `rt-results-import-cyclictest`. Он не пишет SQLite через network
filesystem и не связывает успешность измерения с доступностью сервера.

## Сценарии

| Сценарий | Команда | Ошибка публикации |
|---|---|---|
| Только измерение | runner без `--publish` | Публикация не выполняется |
| Измерение и публикация | runner с `--publish` | Warning, measurement остается complete |
| Existing bundle | publisher с bundle path | Exit status 1 |
| Retry queue | publisher с `--pending` | Неуспешные sidecars остаются pending |

## Автоматическая Публикация

```bash
rt-tester-run-linux-benchmark \
  --config /path/to/cyclictest.conf \
  --duration 10m \
  --publish
```

## Публикация Existing Bundle

```bash
rt-tester-publish-cyclictest \
  --config /path/to/cyclictest.conf \
  ~/.local/state/rt-tester/cyclictest-results/RUN_UID
```

Можно передать несколько bundle paths одной командой.

## Retry Pending

```bash
rt-tester-publish-cyclictest \
  --config /path/to/cyclictest.conf \
  --pending
```

Sidecars хранятся вне finalized bundle. Состояния:

- `publishing`: начата попытка;
- `pending`: remote step завершился ошибкой;
- `published`: importer и remote `run_uid` подтверждены.

Sidecar содержит bundle path, attempts, updated timestamp и last error.
`--pending` пропускает записи, чей bundle directory больше не существует.

## Конфигурация

```ini
[publish]
host = publisher@results.example
port = 22
identity = ~/.ssh/rt-results-publisher
remote-directory = /tmp/rt-tester-cyclictest-publish
importer = /usr/bin/rt-results-import-cyclictest
database = /var/lib/rt-results-prototype/cyclictest.db
state-directory = ~/.local/state/rt-tester/cyclictest-publish
```

| Поле | Обязательно | Default |
|---|---:|---|
| `host` | Да | Нет |
| `port` | Нет | `22` |
| `identity` | Нет | SSH default identity |
| `remote-directory` | Нет | `/tmp/rt-tester-cyclictest-publish` |
| `importer` | Нет | `/usr/bin/rt-results-import-cyclictest` |
| `database` | Нет | `/var/lib/rt-results-prototype/cyclictest.db` |
| `state-directory` | Нет | `~/.local/state/rt-tester/cyclictest-publish` |

Runner SSH settings для target и publisher SSH settings независимы.

## Validation Contract

До network access publisher проверяет:

- bundle schema version 1;
- benchmark type `cyclictest`;
- completion status `complete`;
- canonical UUID `run_uid`;
- наличие declared `cyclictest.json` и `histogram.txt`;
- точное совпадение фактического и declared file set;
- отсутствие artifact paths за пределами bundle;
- size и SHA256 каждого artifact.

После upload server importer повторно валидирует bundle. Publisher проверяет,
что `run_uid` существует в remote `runs` table, и удаляет staging directory.
Повторная отправка того же bundle не создает второй logical run.

## Prerequisites

На PC нужны `ssh`, `scp`, Python 3, writable state directory и noninteractive
SSH authentication. На сервере нужны Python 3, `rt-results-import-cyclictest`,
доступ к catalog DB и права на staging create/remove.

Текущий лабораторный profile использует существующий root SSH. Для общего
стенда используйте отдельного account с ограниченным importer privilege.

## Разделение С Prometheus

Cyclictest publication передает complete bundles в `rt-results`. Prometheus
remote write передает live time-series GPIO/supervised стендов. Эти механизмы
независимы; publisher не использует Prometheus.
