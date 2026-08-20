# Dependencies

## Управляющий ПК

RPM `rt-tester-tools` требует:

```text
python3
python3-module-serial
python3-module-requests
openssh-clients
rsync
coreutils
```

Для source-only plotting дополнительно нужны pandas, numpy и matplotlib.

## Standalone GPIO Target

Package workflow:

```bash
apt-get install rt-handler prometheus-node_exporter openssh-server
```

`rt-handler-0.1.8-alt1` также требует `linux-rt-tests` и `stress-ng`.
Kernelspace profiles требуют совместимый package
`kernel-modules-rt-gpio-responder-6.18`; source и build instructions находятся
в [rt-handler-kernel](https://altlinux.space/besogon1238/rt-handler-kernel).

## Supervised Targets

Runtime и controller boards требуют соответствующие packages из
`rt-supervisor` и `rt-controller`, SSH и при observability node_exporter.
Production PLC заменяет example runtime wrapper своим пакетом.

## Cyclictest Target

```bash
apt-get install linux-rt-tests stress-ng openssh-server
```

Stress-ng нужен только stressed scenario.

## Arduino

Firmware build требует Arduino core и AVR toolchain. Firmware не входит в
`rt-tester-tools`.

## Central Server

Cyclictest catalog и dashboard требуют:

```text
rt-results
grafana
grafana-plugin-frser-sqlite-datasource
```

Central Prometheus deployment дополнительно требует Prometheus и SSH account
для remote-write tunnel.
