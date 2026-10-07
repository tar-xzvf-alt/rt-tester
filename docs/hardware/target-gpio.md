# Target GPIO software

[Русский](../ru/hardware/target-gpio.md)

Standalone response logic is owned externally:
[rt-handler](https://altlinux.space/besogon1238/rt-handler) for userspace and
[rt-handler-kernel](https://altlinux.space/besogon1238/rt-handler-kernel) for the
`rt_gpio_responder` module. This repository does not duplicate target C code.
The supervised GPIO/raw-Ethernet bridge is `controller-emu` from
[rt-controller](https://altlinux.space/besogon1238/rt-controller).

## GPIO mapping

The following is the historical board mapping reference. Confirm the installed
external board profile and your running kernel's GPIO enumeration before wiring.
Bank/line notation is target-specific; none of these numbers is a physical header
pin number.

| Platform | GPIO chip | Request input | Response output |
|---|---|---|---|
| Radxa RK3588 | `/dev/gpiochip3` | BANK=1, LINE=2 | BANK=1, LINE=3 |
| Lichee RV Dock | `/dev/gpiochip0` | BANK=4, LINE=12 | BANK=4, LINE=16 |
| VisionFive 2 | `/dev/gpiochip0` | LINE=60 | LINE=61 |
| BCVM ARM | `/dev/gpiochip0` | LINE=15 | LINE=9 |
| BVC ARM | `/dev/gpiochip0` | LINE=0 | LINE=4 |
| RepkaPI4 | `/dev/gpiochip1` | BANK=6, LINE=13 | BANK=6, LINE=12 |
| MangoPI | `/dev/gpiochip0` | BANK=1, LINE=3 | BANK=1, LINE=4 |
| RockPI4 | `/dev/gpiochip4` | LINE=6 | LINE=7 |

Userspace mappings are in `/etc/rt-handler/boards.d/*.conf` and built-in profiles.
The VisionFive 2 handler board name is `starfive`. Arduino D7 connects through
appropriate level adaptation to request input, response output returns to D20,
and all boards share ground. See [Arduino](arduino.md) and the
[standalone walkthrough](../usage/standalone-gpio-walkthrough.md).

## Installed userspace handler

On ALT Linux with the relevant package repository:

```bash
apt-get install rt-handler prometheus-node_exporter openssh-server
```

Select the board with `rt-handler -b starfive` or its service configuration.
The runner normally starts `/usr/sbin/rt-handler` itself. A running
`node_exporter` is required even without observability: the runner checks/pins
it to `SCHED_OTHER` and housekeeping CPUs. CPU/memory data uses Prometheus;
the legacy userspace text metrics log is not imported and is normally `/dev/null`.
Record handler package/revision, kernel, board profile, IRQ affinity, and FIFO
priority with each experiment.

## Source development

For target source builds, follow the external `rt-handler` instructions. Typical
ALT build dependencies are GCC, make, glibc development headers, libgpiod
development headers, and pkg-config; runtime prerequisites remain separate.

```bash
git clone https://altlinux.space/besogon1238/rt-handler.git
cd rt-handler/src
make
```

The standalone runner supports configured userspace deploy/build paths; see
[standalone mode](../modes/standalone-gpio.md) and
[development and testing](../development/development-and-testing.md). Do not
substitute source-build paths into an installed profile without adapting it.

## Kernelspace responder

Set `execution-mode = kernelspace` and `module = rt_gpio_responder` in the stand
profile. The runner loads the module and checks IRQ diagnostics; it rejects
userspace `--deploy`/`--build`. Only one handler may own the GPIO lines, so stop
the userspace service before module operation or unload the module for userspace.

The external repository's `kernel/rt-handler/README.md` owns build/installation
details. For Linux 6.18 the package name is
`kernel-modules-rt-gpio-responder-6.18`. On a prepared target:

```bash
uname -r
modinfo rt_gpio_responder
# This changes target state; normally let the measurement runner load it:
modprobe rt_gpio_responder board=starfive log_events=0
```

Check `vermagic` against the running kernel and confirm the module's board mapping.
Package naming alone does not establish compatibility.

## Scheduling inspection

`ps -eLo pid,tid,cls,rtprio,psr,comm` reports per-thread scheduling and CPU
placement. `chrt -f -p PRIORITY PID` changes FIFO priority and needs privileges;
record the chosen value. Do not introduce ad-hoc competing workloads into a
controlled run: use the profile's stress configuration and verify cleanup.
