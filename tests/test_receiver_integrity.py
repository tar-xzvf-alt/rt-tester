#!/usr/bin/env python3
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "pc-receiver"))

import database
import run_gpio_measurement as runner


class IntegrityStorageTest(unittest.TestCase):
    def setUp(self):
        database._db_manager = None
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tempdir.name) / "result.db")
        database.init_database(self.db_path)

    def tearDown(self):
        database._db_manager = None
        self.tempdir.cleanup()

    def save_group(self, session_id, *, responses=4, timeouts=0):
        database.save_group_data(
            self.db_path,
            {
                "session_id": session_id,
                "group_index": 0,
                "jitter_us": 1.0,
                "worst_count": 1,
                "worst_latencies_us": [10],
                "requests_sent": 4,
                "responses_received": responses,
                "timeouts": timeouts,
                "parameters": {
                    "interval_us": 1000,
                    "measurements_per_group": 4,
                },
            },
            1,
        )

    def test_complete_group_passes_runner_validation(self):
        self.save_group(101)

        with contextlib.redirect_stdout(io.StringIO()):
            valid = runner.print_db_summary(self.db_path, 101, 1)

        self.assertTrue(valid)

    def test_timeout_group_fails_runner_validation(self):
        self.save_group(102, responses=3, timeouts=1)

        with contextlib.redirect_stdout(io.StringIO()):
            valid = runner.print_db_summary(self.db_path, 102, 1)

        self.assertFalse(valid)


if __name__ == "__main__":
    unittest.main()
