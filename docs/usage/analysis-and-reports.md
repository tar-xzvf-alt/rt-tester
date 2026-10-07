# Analysis and reports

[Русский](../ru/usage/analysis-and-reports.md)

Plotting and database merging run from a source checkout; they are not included
in `rt-tester-tools`. Install pandas, numpy, and matplotlib as described in
[dependencies](../reference/dependencies.md). Commands below run from
`src/pc-receiver/` in that checkout. Replace `DB` with your saved database path
and `SESSION` with an actual session ID.

## Find and validate a session

```bash
./plot_statistics.py DB --limit 250 sessions
./plot_statistics.py DB --limit 250 details SESSION
./plot_statistics.py DB validate --session SESSION
./plot_statistics.py DB latest --stress on
./plot_statistics.py DB latest --stress off
```

`--limit` is a latency threshold in microseconds; the historical methodology
uses `75` for unloaded and `250` for stressed sessions. It is neither a row count
nor the Arduino response deadline. The separate global `--top` option chooses
how many stored worst-tail rows per group enter latency analysis.

SQLite contains the retained worst tail, not every response latency. Plot means,
minima, percentiles, and maxima refer to the selected stored tail. They cannot
reconstruct the whole-group mean or whole-group p95/p99. Stored `jitter_us` is
the firmware's standard deviation over all received responses. Distinguish an
average of group jitters from a pooled standard deviation. See
[measurement statistics](../reference/measurement-statistics.md).

Validate group continuity, request/response/timeout accounting, lifecycle events,
and available trace alignment before comparing. Older data may lack counters or
precise version metadata; state those gaps explicitly. A validator success does
not establish correct wiring or prove a worst-case bound.

## Plot and compare

```bash
./plot_statistics.py DB --session SESSION --limit 250 all
./plot_statistics.py DB --session SESSION --output latency.png latency+soc
./plot_statistics.py DB --session SESSION --output jitter.png jitter+soc
./plot_statistics.py DB trace --session SESSION --output trace.png
./plot_statistics.py DB events --session SESSION --output events.png
./plot_statistics.py DB compare SESSION_A SESSION_B --mode latency
./plot_statistics.py DB compare SESSION_A SESSION_B --mode jitter
./plot_statistics.py DB compare SESSION_A SESSION_B --mode overlay
./plot_statistics.py DB compare SESSION_A SESSION_B --normalize
```

Compare only compatible board, kernel, handler mode, firmware, wiring, workload,
group size, interval, timeout, and CPU/IRQ placement. Normalization is a visual
comparison aid; it removes the absolute latency scale. Check missing SoC data
before interpreting latency/load correlation. See [GPIO methodology](../methodology/gpio-measurements.md).

## Complete report

```bash
./plot_statistics.py DB report --session SESSION --limit 250 \
  --output-dir ./report/session_SESSION
```

Reports contain overview, latency/SoC, jitter/SoC, trace, events, Markdown summary,
and an HTML index where data is available. Preserve the input database and
analysis command alongside the report. The
[standalone walkthrough](standalone-gpio-walkthrough.md) includes a real historical
example, with provenance and metadata limits rather than invented current results.
See the [validation record](../reference/validation.md) for checks actually performed.

## Merge databases

From the repository root:

```bash
python3 src/pc-receiver/merge_databases.py tests merged.db
```

The tool scans only `tests/results_*/*.db` for that input directory, not arbitrary
nested databases or `tests/old_databases/`. It recreates the output database,
copies groups with remapped latency foreign keys, and copies compatible
`soc_metrics` and `events`. It does **not** copy `trace_group_metrics`, raw trace
files, or the entire experimental context. Missing legacy columns can cause
tables to be skipped. Duplicate session/group keys can collapse groups from
different sources; check session uniqueness and the printed source summary.
Keep a separate output path and retain every source database. A merged catalog
is an analysis convenience, not an archival replacement.
