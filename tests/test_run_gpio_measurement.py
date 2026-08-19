#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_gpio_measurement as runner


def config(mode="userspace"):
    cfg = runner.configparser.ConfigParser(interpolation=None)
    target = {
        "host": "root@board",
        "execution-mode": mode,
        "board": "starfive",
        "irq-name": "starfive-monitor",
        "rt-cpu": "1",
        "gpio-irq-priority": "99",
        "housekeeping-cpus": "0,3",
    }
    if mode == "userspace":
        target.update({
            "binary": "/opt/rt-handler",
            "pid-path": "/tmp/rt-handler.pid",
            "stdout-log": "/tmp/rt-handler.log",
            "handler-priority": "85",
        })
    else:
        target.update({
            "module": "rt_gpio_responder",
            "module-args": "board=starfive log_events=0",
            "irq-name": "rt-gpio-responder",
        })
    cfg.read_dict({
        "target": target,
        "measurement": {"target-stress": "on"},
        "stress": {"pid": "/tmp/stress.pid"},
    })
    return cfg


class BackendTest(unittest.TestCase):
    def test_kernel_handler_uses_installed_module(self):
        cfg = config("kernelspace")

        with mock.patch.object(runner, "ssh") as ssh:
            runner.start_handler(cfg, dry_run=False)

        command = ssh.call_args.args[1]
        self.assertIn(
            "modprobe rt_gpio_responder board=starfive log_events=0", command
        )
        self.assertIn("/sys/module/rt_gpio_responder", command)
        self.assertIn("rt-gpio-responder /proc/interrupts", command)

    def test_userspace_pinning_sets_process_and_irq_priorities(self):
        cfg = config("userspace")

        with mock.patch.object(runner, "ssh") as ssh:
            runner.pin_handler(cfg, dry_run=False)

        command = ssh.call_args.args[1]
        self.assertIn("chrt -f -p 85 $tid", command)
        self.assertIn("name=starfive-monitor", command)
        self.assertIn("chrt -f -p 99 $tid", command)
        self.assertIn("taskset -pc 1 $tid", command)

    def test_kernel_pinning_has_no_userspace_pid_dependency(self):
        cfg = config("kernelspace")

        with mock.patch.object(runner, "ssh") as ssh:
            runner.pin_handler(cfg, dry_run=False)

        command = ssh.call_args.args[1]
        self.assertNotIn("rt-handler.pid", command)
        self.assertIn("name=rt-gpio-responder", command)
        self.assertIn("chrt -f -p 99 $tid", command)

    def test_cleanup_unloads_module_and_stops_stress(self):
        cfg = config("kernelspace")

        with mock.patch.object(runner, "ssh") as ssh:
            runner.cleanup_target(cfg, dry_run=False)

        command = ssh.call_args.args[1]
        self.assertIn("modprobe -r rt_gpio_responder", command)
        self.assertIn("pkill -TERM -f '^stress-ng'", command)


class ComparisonConfigTest(unittest.TestCase):
    def test_configs_have_identical_measurement_parameters(self):
        configs = [
            runner.load_config(
                ROOT / "configs/stands/visionfive2-userspace-gpio-stressed.conf"
            ),
            runner.load_config(
                ROOT / "configs/stands/visionfive2-kernelspace-gpio-stressed.conf"
            ),
        ]

        for cfg in configs:
            self.assertEqual(cfg["measurement"]["groups"], "100")
            self.assertEqual(
                cfg["measurement"]["measurements-per-group"], "1500"
            )
            self.assertEqual(
                cfg["measurement"]["measurement-interval-us"], "1000"
            )
            self.assertEqual(
                cfg["measurement"]["response-timeout-us"], "10000"
            )
            self.assertEqual(cfg["measurement"]["target-stress"], "on")
            self.assertEqual(
                cfg["observability"]["prometheus-retention-time"], "24h"
            )

        self.assertEqual(
            configs[0]["measurement"]["db"], configs[1]["measurement"]["db"]
        )
        self.assertEqual(
            configs[0]["observability"]["prometheus-data"],
            configs[1]["observability"]["prometheus-data"],
        )

    def test_idle_configs_match_and_disable_stress(self):
        configs = [
            runner.load_config(
                ROOT / "configs/stands/visionfive2-userspace-gpio-idle.conf"
            ),
            runner.load_config(
                ROOT / "configs/stands/visionfive2-kernelspace-gpio-idle.conf"
            ),
        ]

        for cfg in configs:
            self.assertEqual(cfg["measurement"]["groups"], "100")
            self.assertEqual(cfg["measurement"]["target-stress"], "off")
            self.assertEqual(
                cfg["measurement"]["response-timeout-us"], "10000"
            )
        self.assertEqual(
            configs[0]["measurement"]["db"], configs[1]["measurement"]["db"]
        )

    def test_rt_configs_use_exact_kernel_and_separate_database(self):
        configs = [
            runner.load_config(
                ROOT / "configs/stands/visionfive2-rt-userspace-gpio-stressed.conf"
            ),
            runner.load_config(
                ROOT / "configs/stands/visionfive2-rt-kernelspace-gpio-stressed.conf"
            ),
        ]

        for cfg in configs:
            self.assertEqual(
                cfg["target"]["expected-kernel"],
                "6.18.18-rt-alt1.port.rv64",
            )
            self.assertEqual(
                cfg["measurement"]["target-kernel"],
                "6.18.18-rt-alt1.port.rv64",
            )
            self.assertIn(
                "visionfive2-handler-comparison-rt",
                cfg["measurement"]["db"],
            )
        self.assertEqual(
            configs[0]["measurement"]["db"], configs[1]["measurement"]["db"]
        )


if __name__ == "__main__":
    unittest.main()
