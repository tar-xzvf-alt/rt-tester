# Dependencies and installation

[Русский](../ru/reference/dependencies.md)

## Controlling ALT Linux PC

The standard measurement path uses an installed RPM:

```bash
apt-get install rt-tester-tools
```

This requires a configured package repository providing `rt-tester-tools` and
its dependencies. Project packages and architecture-specific target packages
are not assumed to be available in every ALT repository. If you received a local
RPM, check whether your installed ALT APT supports local-file installation
(`apt-get --help` and its manual), then use the actual supplied filename:

```bash
apt-get install ./rt-tester-tools-VERSION-RELEASE.noarch.rpm
```

If that APT version does not accept local RPMs, use your distribution's supported
local RPM installation workflow. A local RPM does not supply missing dependencies:
they still need compatible repositories or separately supplied RPMs. Do not
disable dependency checks to make installation appear successful.

The package declares Python 3, `python3-module-serial`,
`python3-module-requests`, `openssh-clients`, `rsync`, and `coreutils`. SSH key
authentication must work noninteractively for runners. Use `--help` on installed
commands to confirm the installed tool version's interface.

Prometheus and Grafana are additional PC software for local/central monitoring;
basic GPIO collection disables their startup with `--no-prometheus --no-grafana`.
Central monitoring still needs **local Prometheus** for scraping and queries,
but uses server Grafana through an SSH forward.

Plotting and database merge are currently source-only. Obtain a source checkout
and install compatible pandas, numpy, and matplotlib. ALT package names commonly
used for this are `python3-module-pandas`, `python3-module-numpy`, and
`python3-module-matplotlib`; confirm availability in your repository. The source
receiver also needs serial and requests. Source builds/packaging are documented
in [development and testing](../development/development-and-testing.md).

## Standalone GPIO target

When the target repositories provide compatible packages:

```bash
apt-get install rt-handler prometheus-node_exporter openssh-server
```

The standalone runner requires the `node_exporter` executable **and a running
process even with observability disabled**: it checks the tool and pins its
threads to ordinary scheduling on housekeeping CPUs. Enable/start it using the
target package's service configuration and verify it before collection. Scheduling,
affinity, GPIO access, and optional clock changes need suitable privileges.

The external `rt-handler-0.1.8-alt1` declares `linux-rt-tests` and `stress-ng`
dependencies. Kernelspace profiles need a responder module matching the running
kernel; the Linux 6.18 package is named `kernel-modules-rt-gpio-responder-6.18`.
Availability and installation are controlled by
[rt-handler-kernel](https://altlinux.space/besogon1238/rt-handler-kernel), not this
repository. See [target GPIO](../hardware/target-gpio.md).

## Supervised targets

Runtime/supervisor and controller boards need their corresponding external
`rt-supervisor` and `rt-controller` packages, SSH, raw-socket/GPIO privileges,
and the configured runtime integration. The example runtime comes from
`rt-supervisor-runtime-example`; production PLCs supply their own runtime.
Full observed runs need trace exporters and runtime `node_exporter`. Stress
requires `stress-ng` on the runtime target. See the
[supervised mode](../modes/supervised-raw-ethernet.md) for preflight and topology.

## Cyclictest target

```bash
apt-get install linux-rt-tests openssh-server
# Stressed scenarios only:
apt-get install stress-ng
```

Real-time scheduling and locked memory need appropriate target permissions.

## Arduino and server

Arduino Mega 2560 firmware is separate from the PC RPM. It needs Arduino AVR core,
AVR toolchain, and ArduinoJson; see [Arduino preparation](../hardware/arduino.md).

Your central observability server needs Prometheus with remote-write receiver
support, Grafana, and an SSH account/key for forwarding. See
[server setup](../observability/central.md). A cyclictest catalog additionally
needs the external `rt-results` importer/catalog and, for its SQLite dashboard,
`grafana-plugin-frser-sqlite-datasource`. Those packages/provisioning belong to
`rt-results`; neither the PC RPM nor remote write installs them.
