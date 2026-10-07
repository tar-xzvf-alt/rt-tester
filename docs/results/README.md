# Results Index

[Русский](../ru/results/README.md)

These are historical reports, not results collected while preparing the current
documentation. For a new experiment use the mode guide and methodology; check
current software, wiring, and profiles before reusing a reported command.

| Report | Board/kernel | Scenario |
|---|---|---|
| [Standalone GPIO Baseline](standalone-gpio-baseline.md) | standalone boards | baseline against earlier supervised sessions |
| [VisionFive 2 Non-RT](visionfive2-userspace-vs-kernelspace-non-rt.md) | VisionFive 2 non-RT | userspace vs kernelspace, idle/stress |
| [VisionFive 2 PREEMPT_RT](visionfive2-userspace-vs-kernelspace-preempt-rt.md) | VisionFive 2 PREEMPT_RT | userspace vs kernelspace and cross-kernel comparison |

Some reports identify local artifact paths that are not included in the RPM or
repository. They document provenance, not files available on your machine.
Recorded profiles, versions, and methodology describe known conditions; missing
firmware/handler/kernel details limit reproducibility and should remain explicit.
Numerical latency summaries describe retained worst-tail samples unless stated
otherwise; jitter describes the whole received group. See
[measurement statistics](../reference/measurement-statistics.md).

For a versioned historical database and plot used in the current analysis route,
see the [standalone walkthrough](../usage/standalone-gpio-walkthrough.md).
