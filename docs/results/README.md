# Results Index

Эти документы являются датированными отчетами. Для нового эксперимента
используйте mode guide и methodology, а не копируйте команды из report без
проверки текущих configs.

| Report | Board/kernel | Scenario |
|---|---|---|
| [Standalone GPIO Baseline](standalone-gpio-baseline.md) | standalone boards | baseline against earlier supervised sessions |
| [VisionFive 2 Non-RT](visionfive2-userspace-vs-kernelspace-non-rt.md) | VisionFive 2 non-RT | userspace vs kernelspace, idle/stress |
| [VisionFive 2 PREEMPT_RT](visionfive2-userspace-vs-kernelspace-preempt-rt.md) | VisionFive 2 PREEMPT_RT | userspace vs kernelspace and cross-kernel comparison |

Некоторые reports ссылаются на локальные artifact paths, которые не входят в
RPM и repository. Воспроизводимыми источниками являются указанные stand configs,
kernel/package versions и methodology.
