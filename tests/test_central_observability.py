#!/usr/bin/env python3
import configparser
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import central_observability


def config():
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_dict({
        "stand": {"name": "visionfive2-gpio"},
        "observability": {
            "collector-label": "lab-pc",
            "remote-write-url": "http://127.0.0.1:19090/api/v1/write",
            "central-ssh-host": "prometheus-writer@metrics.example",
            "central-ssh-port": "228",
            "central-ssh-identity": "~/.ssh/metrics-writer",
            "grafana-managed": "false",
            "grafana-url": "http://127.0.0.1:13000/d/dashboard",
        },
    })
    return cfg


class CentralObservabilityTest(unittest.TestCase):
    def test_prometheus_config_fragments_include_identity(self):
        cfg = config()

        labels = central_observability.external_labels(cfg, "rt-stand")
        remote_write = central_observability.remote_write_block(cfg)

        self.assertIn('monitor: "rt-stand"', labels)
        self.assertIn('collector: "lab-pc"', labels)
        self.assertIn('stand: "visionfive2-gpio"', labels)
        self.assertIn("remote_write:", remote_write)
        self.assertIn("http://127.0.0.1:19090/api/v1/write", remote_write)

    def test_remote_grafana_is_not_started_locally(self):
        cfg = config()

        self.assertFalse(central_observability.managed_grafana(cfg))
        self.assertEqual(
            central_observability.grafana_url(cfg),
            "http://127.0.0.1:13000/d/dashboard",
        )

    def test_dry_run_tunnel_has_both_forwardings(self):
        cfg = config()
        with (
            mock.patch.object(central_observability, "_http_ok", return_value=False),
            mock.patch("builtins.print") as output,
        ):
            central_observability.start_tunnel(cfg, dry_run=True)

        command = output.call_args.args[0]
        self.assertIn("127.0.0.1:19090:127.0.0.1:9090", command)
        self.assertIn("127.0.0.1:13000:127.0.0.1:3000", command)
        self.assertIn("prometheus-writer@metrics.example", command)
        self.assertIn(str(Path("~/.ssh/metrics-writer").expanduser()), command)


if __name__ == "__main__":
    unittest.main()
