# Publishing cyclictest results

[Русский](../ru/usage/publish-cyclictest.md)

The publisher uploads a validated cyclictest bundle and invokes the external
server's `rt-results-import-cyclictest`. It does not write SQLite over a network
filesystem. Measurement completion is independent of server availability.

| Workflow | Invocation | Publication failure |
|---|---|---|
| Collection only | Runner without `--publish` | No publication attempted |
| Collection and publication | Runner with `--publish` | Warning; measurement stays complete |
| Existing bundle | Publisher with bundle path(s) | Exit status `1` |
| Retry queue | Publisher with `--pending` | Failed sidecars stay pending |

```bash
rt-tester-run-linux-benchmark --config ./cyclictest.conf \
  --duration 10m --publish
rt-tester-publish-cyclictest --config ./cyclictest.conf \
  ~/.local/state/rt-tester/cyclictest-results/RUN_UID
rt-tester-publish-cyclictest --config ./cyclictest.conf --pending
```

You can pass several finalized bundle paths. Sidecars live outside bundles, so
retries do not modify immutable evidence. States are `publishing`, `pending`, and
`published`; records contain bundle path, attempts, update time, and last error.
`--pending` skips records whose bundle directories no longer exist.

## Configure your server

```ini
[publish]
host = publisher@RESULTS_HOST
port = 22
identity = ~/.ssh/rt-results-publisher
remote-directory = /tmp/rt-tester-cyclictest-publish
importer = /usr/bin/rt-results-import-cyclictest
database = /var/lib/rt-results-prototype/cyclictest.db
state-directory = ~/.local/state/rt-tester/cyclictest-publish
```

Only `host` is required. Other defaults are shown above except `identity`, which
defaults to SSH's identity selection. Target SSH and publication SSH settings are
independent. The PC needs Python 3, `ssh`, `scp`, writable state, and noninteractive
authentication. The server needs Python 3, the importer from `rt-results`, a
writable catalog database, and staging create/remove permissions. Repository
and package availability must be established for your server separately. Use an
account with appropriate importer/catalog permissions; laboratory root access is
not a portable prerequisite.

## Validation contract

Before network access the publisher checks schema version `1`, benchmark type
`cyclictest`, status `complete`, canonical UUID `run_uid`, declared
`cyclictest.json`/`histogram.txt`, exact declared file set, paths confined to the
bundle, and every file's size/SHA256. This bundle schema is separate from the
unused GPIO SQLite `schema_version` table.

After upload the server importer validates again. The publisher confirms the
remote `runs` table contains `run_uid` and removes staging. Re-uploading the same
bundle does not create another logical run. Preserve the original bundle and
sidecar if diagnosing publication problems.

This workflow publishes complete bundles into the `rt-results` catalog.
[Prometheus remote write](../observability/central.md) sends live GPIO/supervised
time series and does not upload their SQLite databases. The two mechanisms are
independent.
