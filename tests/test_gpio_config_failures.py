#!/usr/bin/env python3
import argparse
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_gpio_measurement as runner
import run_linux_benchmark
import run_stand_measurement


class ConfigurationFailureTest(unittest.TestCase):
    def test_captured_machine_output_excludes_stderr_diagnostics(self):
        command = [sys.executable, "-c",
                   "import sys; print('expected-kernel'); print('SSH diagnostic', file=sys.stderr)"]
        for module in (runner, run_linux_benchmark, run_stand_measurement):
            with self.subTest(runner=module.__name__), contextlib.redirect_stdout(io.StringIO()):
                result = module.run(command, capture=True)
                self.assertEqual(result.stdout.strip(), "expected-kernel")

    def test_kernel_mismatch_reports_actual_and_expected(self):
        cfg = runner.load_config(ROOT / "configs/stands/visionfive2-rt-userspace-gpio-idle.conf")
        result = subprocess.CompletedProcess([], 0, "different-kernel\n", "")
        with mock.patch.object(runner, "ssh", return_value=result), \
             mock.patch.object(runner.shutil, "which", return_value="/bin/tool"):
            with self.assertRaisesRegex(SystemExit, "different-kernel.*6.18.18-rt"):
                runner.check_prerequisites(cfg, dry_run=False,
                                           need_deploy=False, need_build=False)

    def test_ssh_connection_attempt_is_bounded(self):
        for module in (runner, run_linux_benchmark, run_stand_measurement):
            with self.subTest(runner=module.__name__), mock.patch.object(module, "run") as execute:
                module.ssh("root@unreachable", "true")
                self.assertIn("ConnectTimeout=5", execute.call_args.args[0])

    def test_explicit_exporter_endpoint_remains_supported(self):
        cfg = runner.load_config(ROOT / "configs/stands/examples/visionfive2-gpio-local.conf")
        cfg["target"]["host"] = "root@192.0.2.41"
        cfg["observability"]["node-exporter-target"] = "exporter.example:19100"
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "prometheus.yml"
            runner.write_prometheus_config(output, cfg)
            self.assertIn("exporter.example:19100", output.read_text())

    def test_blank_exporter_endpoint_uses_target_host(self):
        cfg = runner.load_config(ROOT / "configs/stands/examples/visionfive2-gpio-local.conf")
        cfg["target"]["host"] = "root@192.0.2.41"
        cfg["observability"]["node-exporter-target"] = ""
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "prometheus.yml"
            runner.write_prometheus_config(output, cfg)
            self.assertIn("192.0.2.41:9100", output.read_text())

    def test_exporter_follows_edited_standalone_host(self):
        paths = list((ROOT / "configs/stands").glob("visionfive2*gpio*.conf"))
        paths += list((ROOT / "configs/stands/examples").glob("*.conf"))
        for path in paths:
            with self.subTest(profile=path.name), tempfile.TemporaryDirectory() as tmp:
                cfg = runner.load_config(path)
                cfg["target"]["host"] = "root@192.0.2.41"
                generated = Path(tmp) / "prometheus.yml"
                runner.write_prometheus_config(generated, cfg)
                self.assertIn("192.0.2.41:9100", generated.read_text())

    def test_output_path_survives_receiver_working_directory_change(self):
        for requested in ("relative/result.db", "~/result.db", "$CONFIG_AUDIT_HOME/result.db"):
            with self.subTest(path=requested), tempfile.TemporaryDirectory() as tmp:
                cfg = runner.load_config(ROOT / "configs/stands/examples/visionfive2-gpio-basic.conf")
                cfg["measurement"]["db"] = requested
                cfg["measurement"]["groups"] = "3"
                profile = Path(tmp) / "profile.conf"
                with profile.open("w") as output:
                    cfg.write(output)
                args = argparse.Namespace(config=str(profile), session_id=123, groups=3,
                    db=None, warmup_seconds=None, stop_observability=False, dry_run=False,
                    deploy=False, build=False, prepare_only=False, skip_time_sync=True,
                    no_prometheus=True, no_grafana=True, keep_target=False)
                seen = []

                def collect(cfg, sid, params, groups, **kwargs):
                    emitted = dict(line.split(" = ", 1) for line in params.read_text().splitlines() if line)
                    path = Path(emitted["db"])
                    self.assertTrue(path.is_absolute(), emitted["db"])
                    self.assertNotIn("~", str(path))
                    self.assertNotIn("$", str(path))
                    self.assertEqual(path, Path(os.path.expandvars(requested)).expanduser().resolve())
                    seen.append(path)

                old_cwd = Path.cwd()
                with contextlib.ExitStack() as stack:
                    stack.enter_context(mock.patch.dict(os.environ, {"HOME": tmp, "CONFIG_AUDIT_HOME": tmp}))
                    stack.enter_context(mock.patch.object(runner.tempfile, "gettempdir", return_value=tmp))
                    for name in ("check_prerequisites", "check_arduino", "cleanup_target", "stop_target",
                                 "stop_local_receivers", "start_stress", "pin_node_exporter",
                                 "warm_up_stress", "start_handler", "pin_handler",
                                 "print_target_diagnostics", "print_prometheus_diagnostics"):
                        stack.enter_context(mock.patch.object(runner, name))
                    stack.enter_context(mock.patch.object(runner, "run_receiver", side_effect=collect))
                    summary = stack.enter_context(mock.patch.object(runner, "print_db_summary", return_value=True))
                    stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                    os.chdir(tmp)
                    try:
                        runner.run_measurement(args)
                        self.assertEqual(Path(summary.call_args.args[0]), seen[0])
                    finally:
                        os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
