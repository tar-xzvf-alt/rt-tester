# RT Tester

[Русский](docs/ru/README.md)

`rt-tester` helps experiment engineers measure Linux response latency, preserve
the measurement evidence, and compare results under recorded conditions.
The reference experiment uses a VisionFive 2, Arduino Mega 2560, and ALT Linux.

```text
Measurement PC ──USB/serial── Arduino Mega
                              D7 │ request through level adaptation
                                 ▼
                          VisionFive 2 GPIO → handler
                                 │ response through level adaptation
                             D20 ◀
Arduino times request → response; PC stores group data in SQLite.
All boards share GND. GPIO wiring must respect the boards' voltage levels.
```

This physical round trip includes GPIO and handler response time. A separate
`cyclictest` mode measures scheduler wake-up latency without Arduino.

## Start an experiment

On the controlling ALT Linux PC, install the tools from a repository that
provides the package:

```bash
apt-get install rt-tester-tools
```

Package availability depends on your configured repositories or supplied local
RPMs; this command does not imply that every ALT repository contains the project
packages. See [installation and prerequisites](docs/reference/dependencies.md).
Target software and Arduino firmware are installed separately.

Follow the [complete standalone GPIO walkthrough](docs/usage/standalone-gpio-walkthrough.md)
to prepare hardware, copy and edit a profile in a saved experiment directory,
run a short check, collect data, validate it, and analyze a historical example.
The basic profile requires `--no-prometheus --no-grafana`; even this mode needs
a running target `node_exporter` because the runner checks and pins it.

| Your task | Start here |
|---|---|
| Prepare your first stand and choose a mode | [Getting started](docs/getting-started.md) |
| Run the complete VisionFive 2 GPIO experiment | [Standalone walkthrough](docs/usage/standalone-gpio-walkthrough.md) |
| Measure the runtime/supervisor/controller path | [Supervised raw Ethernet](docs/modes/supervised-raw-ethernet.md) |
| Measure scheduler latency | [Linux benchmarks](docs/modes/linux-benchmarks.md) |
| Validate and interpret SQLite data | [Analysis and reports](docs/usage/analysis-and-reports.md) |
| See live data locally or on your server | [Local](docs/observability/local.md) / [central observability](docs/observability/central.md) |
| Maintain or extend the tools | [Development and testing](docs/development/development-and-testing.md) |

The [documentation index](docs/README.md) includes methodology, statistics,
hardware references, and dated results. Live Prometheus delivery does **not**
publish the primary SQLite database.

## Repository responsibilities

This repository owns PC runners, receiver, stand profiles, and observability
assets. Target components have their own source of truth:

- [rt-handler](https://altlinux.space/besogon1238/rt-handler): userspace GPIO;
- [rt-handler-kernel](https://altlinux.space/besogon1238/rt-handler-kernel): kernel GPIO responder;
- [rt-supervisor](https://altlinux.space/besogon1238/rt-supervisor): supervisor/runtime integration;
- [rt-controller](https://altlinux.space/besogon1238/rt-controller): GPIO/raw-Ethernet bridge;
- [rt-results](https://altlinux.space/besogon1238/rt-results): validated imports, catalogs, and result dashboards.

Developers should start with [architecture](docs/development/architecture.md),
then [development and testing](docs/development/development-and-testing.md) and
the [change guide](docs/development/change-guide.md). Source builds and RPM
packaging belong to that route; installed packages are the normal measurement
execution path. Plotting currently requires a source checkout.

## License

GNU GPL v3; see [LICENSE.md](LICENSE.md).
