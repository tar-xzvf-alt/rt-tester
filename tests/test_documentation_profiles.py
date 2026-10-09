#!/usr/bin/env python3
"""Exercise documented profiles through generators without touching a stand."""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_gpio_measurement as runner


class ReferenceProfileTest(unittest.TestCase):
    def test_variants_preserve_measurement_and_receiver_contract(self):
        measurements = []
        for variant in ("basic", "local", "central"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as tmp:
                source = ROOT / "configs/stands/examples" / (
                    f"visionfive2-gpio-{variant}.conf"
                )
                adapted = Path(tmp) / "profile.conf"
                state = Path(tmp) / ".rt-tester-example"
                state.mkdir()
                text = source.read_text().replace("TARGET_HOST", "192.0.2.10")
                text = text.replace("TARGET_KERNEL", "test-kernel")
                text = text.replace(".rt-tester-example", str(state))
                text = text.replace("CENTRAL_HOST", "results.example")
                adapted.write_text(text)
                cfg = runner.load_config(adapted)
                parameters = dict(cfg["measurement"])
                parameters.pop("db")  # Each isolated case has its own output path.
                measurements.append(parameters)
                receiver_path = state / "receiver.conf"
                runner.write_receiver_config(
                    receiver_path, cfg, cfg["measurement"]["db"], 100
                )
                emitted = dict(
                    line.split(" = ", 1)
                    for line in receiver_path.read_text().splitlines() if line
                )
                self.assertTrue(Path(emitted["db"]).is_absolute())
                self.assertEqual(emitted["response-timeout-us"], "10000")
                self.assertEqual(emitted["measurements-per-group"], "1500")
                self.assertEqual(emitted["measurement-interval-us"], "1000")
                self.assertEqual(emitted["auto-stop-groups"], "100")
                self.assertEqual(emitted["target-kernel"], "test-kernel")
                self.assertEqual(emitted["prometheus-url"], "http://127.0.0.1:9092")

                prometheus = state / "prometheus.yml"
                runner.write_prometheus_config(prometheus, cfg)
                scrape = prometheus.read_text()
                self.assertIn("127.0.0.1:9101", scrape)
                self.assertIn("192.0.2.10:9100", scrape)
                if variant == "central":
                    self.assertIn("remote_write:", scrape)
                    self.assertIn("http://127.0.0.1:19090/api/v1/write", scrape)
                    self.assertFalse(runner.central_observability.managed_grafana(cfg))
                else:
                    self.assertNotIn("remote_write:", scrape)
                if variant == "local":
                    self.assertTrue(runner.central_observability.managed_grafana(cfg))
                    provision = runner.write_grafana_provisioning(
                        state / "provisioning", cfg, "http://127.0.0.1:9092"
                    )
                    datasource = (provision / "datasources/rt-gpio-prometheus.yml").read_text()
                    self.assertIn("uid: rt-gpio-prometheus", datasource)
                    self.assertIn("url: http://127.0.0.1:9092", datasource)
        self.assertEqual(measurements[0], measurements[1])
        self.assertEqual(measurements[1], measurements[2])

    def test_basic_documented_flags_skip_observability_lifecycle(self):
        cfg_path = ROOT / "configs/stands/examples/visionfive2-gpio-basic.conf"
        args = runner.argparse.Namespace(
            config=str(cfg_path), session_id=123, groups=3, db="/tmp/example.db",
            warmup_seconds=None, stop_observability=False, dry_run=False,
            deploy=False, build=False, prepare_only=False, skip_time_sync=True,
            no_prometheus=True, no_grafana=True, keep_target=False,
        )
        mocked = (
            "check_prerequisites", "check_arduino", "cleanup_target", "stop_target",
            "stop_local_receivers", "start_stress", "pin_node_exporter",
            "warm_up_stress", "start_handler", "pin_handler", "run_receiver",
            "print_target_diagnostics", "print_db_summary", "write_receiver_config",
        )
        with contextlib.ExitStack() as stack:
            for name in mocked:
                stack.enter_context(mock.patch.object(runner, name, return_value=True))
            stack.enter_context(mock.patch.object(runner.Path, "mkdir"))
            prom = stack.enter_context(mock.patch.object(runner, "start_prometheus"))
            grafana = stack.enter_context(mock.patch.object(runner, "start_grafana"))
            tunnel = stack.enter_context(mock.patch.object(
                runner.central_observability, "start_tunnel"
            ))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            runner.run_measurement(args)
            prom.assert_not_called()
            grafana.assert_not_called()
            tunnel.assert_not_called()


if __name__ == "__main__":
    unittest.main()
