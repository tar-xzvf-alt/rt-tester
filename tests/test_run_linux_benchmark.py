#!/usr/bin/env python3
import configparser
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_linux_benchmark as runner


def config():
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_dict({
        "stand": {"name": "board-cyclictest"},
        "target": {"host": "root@board", "label": "board"},
        "benchmark": {
            "engine": "cyclictest",
            "duration": "60",
            "histogram-max-us": "1000",
        },
        "workload": {"engine": "idle"},
        "results": {"output-root": "/tmp/results"},
    })
    return cfg


class CyclictestCommandTest(unittest.TestCase):
    def test_command_is_machine_readable_and_all_cpu(self):
        command = runner.cyclictest_command(config(), "/tmp/run")

        self.assertIn("--smp", command)
        self.assertIn("--json=/tmp/run/cyclictest.json", command)
        self.assertIn("--histogram=1000", command)
        self.assertIn("--histfile=/tmp/run/histogram.txt", command)
        self.assertIn("--duration=60", command)
        self.assertIn("--quiet", command)


class CyclictestValidationTest(unittest.TestCase):
    def test_valid_result_reports_histogram_overflow(self):
        payload = {
            "file_version": 1,
            "return_code": 0,
            "num_threads": 2,
            "thread": {
                "0": {
                    "cycles": 3, "min": 1, "max": 10, "avg": 4.0,
                    "cpu": 0, "node": 0, "histogram": {"1": 1, "2": 1},
                },
                "1": {
                    "cycles": 2, "min": 2, "max": 3, "avg": 2.5,
                    "cpu": 1, "node": 0, "histogram": {"2": 1, "3": 1},
                },
            },
        }

        summary = runner.validate_cyclictest(payload)

        self.assertEqual(summary["threads"], 2)
        self.assertEqual(summary["cycles"], 5)
        self.assertEqual(summary["histogram_overflow"], 1)

    def test_rejects_thread_count_mismatch(self):
        payload = {
            "file_version": 1,
            "return_code": 0,
            "num_threads": 2,
            "thread": {"0": {}},
        }

        with self.assertRaisesRegex(ValueError, "thread count"):
            runner.validate_cyclictest(payload)


class StressLifecycleTest(unittest.TestCase):
    def test_stress_uses_dedicated_process_group(self):
        cfg = config()
        cfg.set("workload", "engine", "stress-ng")
        cfg.set("workload", "command", "stress-ng --cpu 4 --timeout 0")
        cfg.set("workload", "warmup-seconds", "0")

        with mock.patch.object(runner, "ssh") as ssh:
            runner.start_stress(cfg, "/tmp/run")
            runner.stop_stress(cfg, "/tmp/run")

        start_command = ssh.call_args_list[0].args[1]
        stop_command = ssh.call_args_list[1].args[1]
        self.assertIn("setsid", start_command)
        self.assertIn("/tmp/run/stress.pid", start_command)
        self.assertIn("kill -TERM -$p", stop_command)
        self.assertNotIn("pkill", stop_command)


class PreflightTest(unittest.TestCase):
    def test_stress_records_package_version(self):
        cfg = config()
        cfg.set("workload", "engine", "stress-ng")

        with (
            mock.patch.object(runner, "ssh"),
            mock.patch.object(runner, "collect_target_metadata", return_value={}),
            mock.patch.object(
                runner,
                "remote_value",
                return_value="stress-ng-0.21.04-alt1.riscv64",
            ) as remote_value,
        ):
            metadata = runner.preflight(cfg)

        self.assertEqual(
            metadata["stress_package"],
            "stress-ng-0.21.04-alt1.riscv64",
        )
        remote_value.assert_called_once_with("root@board", "rpm -q stress-ng")


if __name__ == "__main__":
    unittest.main()
