#!/usr/bin/env python3
import configparser
import hashlib
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import publish_cyclictest as publisher


class CyclictestPublisherTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        artifact = self.bundle / "cyclictest.json"
        artifact.write_text("{}\n", encoding="utf-8")
        histogram = self.bundle / "histogram.txt"
        histogram.write_text("# histogram\n", encoding="utf-8")
        self.run_uid = str(uuid.uuid4())
        manifest = {
            "schema_version": 1,
            "run_uid": self.run_uid,
            "benchmark_type": "cyclictest",
            "completion_status": "complete",
            "artifacts": [
                {
                    "path": artifact.name,
                    "size": artifact.stat().st_size,
                    "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                },
                {
                    "path": histogram.name,
                    "size": histogram.stat().st_size,
                    "sha256": hashlib.sha256(histogram.read_bytes()).hexdigest(),
                },
            ],
        }
        (self.bundle / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        self.cfg = configparser.ConfigParser(interpolation=None)
        self.cfg.read_dict({
            "publish": {
                "host": "publisher@results.example",
                "port": "228",
                "database": "/var/lib/rt-results-prototype/cyclictest.db",
                "state-directory": str(self.root / "state"),
            }
        })

    def tearDown(self):
        self.temporary.cleanup()

    def test_publish_validates_import_and_records_state(self):
        commands = []

        def execute(command, *, check=True):
            commands.append((command, check))

        publisher.publish_bundle(self.bundle, self.cfg, execute=execute)

        self.assertTrue(any(command[0] == "scp" for command, _ in commands))
        self.assertTrue(any(
            "rt-results-import-cyclictest" in command[-1]
            for command, _ in commands
        ))
        self.assertTrue(any(
            "SELECT 1 FROM runs WHERE run_uid" in command[-1]
            for command, _ in commands
        ))
        state = json.loads(
            (self.root / "state" / f"{self.run_uid}.json").read_text()
        )
        self.assertEqual(state["status"], "published")
        self.assertEqual(state["attempts"], 1)

    def test_failure_remains_pending_for_retry(self):
        def execute(command, *, check=True):
            if command[0] == "scp":
                raise OSError("network unavailable")

        with self.assertRaisesRegex(OSError, "network unavailable"):
            publisher.publish_bundle(self.bundle, self.cfg, execute=execute)

        state = json.loads(
            (self.root / "state" / f"{self.run_uid}.json").read_text()
        )
        self.assertEqual(state["status"], "pending")
        self.assertEqual(publisher.pending_bundles(self.cfg), [self.bundle])

    def test_rejects_modified_artifact(self):
        (self.bundle / "cyclictest.json").write_text("modified\n")

        with self.assertRaisesRegex(ValueError, "artifact size mismatch"):
            publisher.validate_bundle(self.bundle)

    def test_rejects_undeclared_file(self):
        (self.bundle / "secret.txt").write_text("not declared\n")

        with self.assertRaisesRegex(ValueError, "do not match"):
            publisher.validate_bundle(self.bundle)


if __name__ == "__main__":
    unittest.main()
