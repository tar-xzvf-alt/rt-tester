#!/usr/bin/env python3
import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_stand_measurement as runner


class OutputTest(unittest.TestCase):
    def setUp(self):
        runner.VERBOSE = False

    def tearDown(self):
        runner.VERBOSE = False

    def test_concise_run_hides_command_and_child_output(self):
        completed = subprocess.CompletedProcess(["tool"], 0, "details\n", None)
        output = io.StringIO()
        with (
            mock.patch.object(runner.subprocess, "run", return_value=completed),
            contextlib.redirect_stdout(output),
        ):
            result = runner.run(["tool"])

        self.assertEqual(result.stdout, "details\n")
        self.assertEqual(output.getvalue(), "")

    def test_verbose_capture_prints_command_and_child_output(self):
        runner.VERBOSE = True
        completed = subprocess.CompletedProcess(["tool"], 0, "details\n", None)
        output = io.StringIO()
        with (
            mock.patch.object(runner.subprocess, "run", return_value=completed),
            contextlib.redirect_stdout(output),
        ):
            runner.run(["tool"], capture=True)

        self.assertEqual(output.getvalue(), "$ tool\ndetails\n")

    def test_dry_run_always_prints_command(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            runner.run(["tool", "argument"], dry_run=True)

        self.assertEqual(output.getvalue(), "$ tool argument\n")

    def test_receiver_prints_every_group_but_hides_banner(self):
        process = mock.Mock()
        process.stdout = io.StringIO(
            "configuration details\n"
            "Group 1/2 stored (index 0, 50.0%)\n"
            "Group 2/2 stored (index 1, 100.0%)\n"
        )
        process.wait.return_value = 0
        output = io.StringIO()
        with (
            mock.patch.object(runner.subprocess, "Popen", return_value=process),
            contextlib.redirect_stdout(output),
        ):
            runner.run_receiver(mock.Mock(), 42, Path("/tmp/config"), 2,
                                dry_run=False)

        self.assertEqual(
            output.getvalue(),
            "Progress: 1/2 groups\nProgress: 2/2 groups\n",
        )

    def test_command_failure_is_actionable_without_traceback(self):
        error = subprocess.CalledProcessError(
            255, ["ssh", "host"], output="connection refused\n"
        )
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            runner.report_command_failure(error)

        text = output.getvalue()
        self.assertIn("exit status 255", text)
        self.assertIn("command: ssh host", text)
        self.assertIn("connection refused", text)
        self.assertIn("--verbose", text)
        self.assertNotIn("Traceback", text)

    def test_trace_import_failure_is_an_anomaly(self):
        completed = subprocess.CompletedProcess(["import"], 1, "failed\n", None)
        output = io.StringIO()
        with (
            mock.patch.object(runner, "run", return_value=completed),
            mock.patch.object(runner.time, "sleep"),
            contextlib.redirect_stdout(output),
        ):
            result = runner.import_trace_metrics(
                "/tmp/result.db", 42, "http://127.0.0.1:9091", dry_run=False
            )

        self.assertFalse(result)
        self.assertIn("trace metric import failed", output.getvalue())


class HelpTest(unittest.TestCase):
    def test_help_uses_public_command_and_documents_simple_start(self):
        help_text = runner.build_parser().format_help()

        self.assertTrue(help_text.startswith("usage: rt-tester-run-stand"))
        self.assertIn("Standard test:", help_text)
        self.assertIn(
            "--config /usr/share/rt-tester-tools/configs/stands/"
            "rockpi-beremiz-visionfive2-controller.conf",
            help_text,
        )
        self.assertIn("--verbose", help_text)

    def test_grafana_url_includes_session(self):
        self.assertEqual(
            runner.grafana_session_url(
                "http://127.0.0.1:3001/d/rt-trace-stages", 123
            ),
            "http://127.0.0.1:3001/d/rt-trace-stages?var-session_id=123",
        )


class NetworkPolicyTest(unittest.TestCase):
    def setUp(self):
        runner.VERBOSE = False

    def snapshots(self, *, dropped=0, squeeze=0, rx_drop=0):
        before = {
            "controller": {
                "host": "root@board",
                "iface": "end0",
                "dev": {"rx_drop": 10},
                "softnet": {"dropped": 20, "time_squeeze": 30},
                "softnet_per_cpu": [
                    {"cpu": 0, "dropped": 10, "time_squeeze": 10},
                    {"cpu": 1, "dropped": 10, "time_squeeze": 20},
                ],
                "ethtool": {},
            }
        }
        after = {
            "controller": {
                "host": "root@board",
                "iface": "end0",
                "dev": {"rx_drop": 10 + rx_drop},
                "softnet": {
                    "dropped": 20 + dropped,
                    "time_squeeze": 30 + squeeze,
                },
                "softnet_per_cpu": [
                    {"cpu": 0, "dropped": 10 + dropped, "time_squeeze": 10},
                    {"cpu": 1, "dropped": 10, "time_squeeze": 20 + squeeze},
                ],
                "ethtool": {},
            }
        }
        return before, after

    def test_time_squeeze_is_warning_not_failure(self):
        before, after = self.snapshots(squeeze=3)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = runner.print_network_delta(before, after)

        self.assertTrue(result)
        self.assertIn("softnet.time_squeeze", output.getvalue())
        self.assertIn("cpu1=+3", output.getvalue())
        self.assertIn("no packet loss implied", output.getvalue())

    def test_softnet_drop_is_failure(self):
        before, after = self.snapshots(dropped=1)

        self.assertFalse(runner.print_network_delta(before, after))

    def test_interface_drop_is_failure(self):
        before, after = self.snapshots(rx_drop=1)

        self.assertFalse(runner.print_network_delta(before, after))


class ControllerLaunchTest(unittest.TestCase):
    def test_expected_group_count_is_passed_to_controller(self):
        cfg = runner.configparser.ConfigParser(interpolation=None)
        cfg.read_dict({
            "controller": {
                "host": "root@controller",
                "repo": "/usr/share/rt-controller",
                "iface": "end0",
                "board": "visionfive2",
                "binary": "/usr/bin/controller-emu",
                "trace-path": "/tmp/trace.jsonl",
                "log-path": "/tmp/controller.log",
                "pid-path": "/tmp/controller.pid",
                "stand-config": "configs/stand/controller.conf",
            },
            "measurement": {"measurements-per-group": "100"},
        })

        with mock.patch.object(runner, "ssh") as ssh:
            runner.start_controller(cfg, 123, 2, dry_run=False)

        command = ssh.call_args.args[1]
        self.assertIn("RT_TRACE_SESSION_ID=123", command)
        self.assertIn("RT_TRACE_MEASUREMENTS_PER_GROUP=100", command)
        self.assertIn("RT_TRACE_EXPECTED_GROUPS=2", command)

if __name__ == "__main__":
    unittest.main()
