# RT Tester documentation

[Русский](ru/README.md)

## Experiment engineer route

Start with [getting started](getting-started.md), then the
[complete standalone GPIO walkthrough](usage/standalone-gpio-walkthrough.md).
It covers the VisionFive 2 / Arduino Mega 2560 / ALT Linux stand, installed
tools, reader-owned profiles, collection, integrity, and interpretation.

| Stage | Documents |
|---|---|
| Prepare | [Dependencies](reference/dependencies.md), [Arduino](hardware/arduino.md), [target GPIO](hardware/target-gpio.md) |
| Choose what to measure | [Standalone GPIO](modes/standalone-gpio.md), [supervised raw Ethernet](modes/supervised-raw-ethernet.md), [Linux benchmarks](modes/linux-benchmarks.md) |
| Collect and preserve | [Receiver](usage/receiver.md), [runtime paths](reference/runtime-paths.md), [SQLite schema](reference/sqlite-schema.md) |
| Verify and interpret | [Analysis and reports](usage/analysis-and-reports.md), [measurement statistics](reference/measurement-statistics.md), [validation record](reference/validation.md) |
| Design comparisons | [GPIO methodology](methodology/gpio-measurements.md), [cyclictest comparisons](methodology/cyclictest-comparisons.md) |
| Observe or publish | [Local observability](observability/local.md), [central observability](observability/central.md), [publish cyclictest](usage/publish-cyclictest.md) |
| Consult past evidence | [Dated results](results/README.md) |

SQLite is the primary GPIO/supervised artifact. Prometheus is live monitoring,
not database publication. Historical reports record earlier conditions and do
not substitute for a current installation or wiring procedure.

## Developer route

1. [Architecture](development/architecture.md): modules, interfaces, data flow.
2. [Development and testing](development/development-and-testing.md): source
   setup, focused checks, and packaging workflow.
3. [Change guide](development/change-guide.md): where to make a change and what
   to verify.

## Documentation maintenance

English is canonical at existing paths. Russian mirrors reader documents in
`ru/`; update commands, definitions, limitations, and language switches together.
Keep README compact and engineer-first. Each mode has one canonical mode guide;
workflows belong in `usage/`, experimental controls in `methodology/`, formats
and paths in `reference/`, and dated numerical evidence in `results/`.
Keep operational instructions independent of private hostnames and author paths.
Validation records distinguish static/offline checks from physical measurements
and server walkthroughs.
