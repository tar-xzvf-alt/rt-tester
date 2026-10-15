import sys
import subprocess
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "pc-receiver"))

import metrics_server
import prometheus_client


class LiveObservabilityTest(unittest.TestCase):
    def test_session_totals_include_losses_from_earlier_groups(self):
        store = metrics_server.MetricsStorage()
        store.update_session('123')
        first = {'board': 'spacemit-k3', 'kernel': 'test', 'stress': 'off',
                 'group_index': 0, 'requests_sent': 20, 'responses_received': 19, 'timeouts': 1}
        store.add_group(first)
        store.add_group(first)  # A repeated group must not inflate counters.
        store.add_group({**first, 'group_index': 1, 'responses_received': 20, 'timeouts': 0})
        handler = object.__new__(metrics_server.PrometheusMetricsHandler)
        handler.storage = store
        body = handler.generate_metrics()
        labels = 'board="spacemit-k3",kernel="test",session_id="123",stress="off"'
        self.assertIn(f'arduino_requests_total{{{labels}}} 40', body)
        self.assertIn(f'arduino_responses_total{{{labels}}} 39', body)
        self.assertIn(f'arduino_timeouts_total{{{labels}}} 1', body)

    def test_receiver_can_keep_endpoint_after_a_finite_session(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / 'src/pc-receiver/receiver.py'), '--help'],
            capture_output=True, text=True, check=True,
        )
        self.assertIn('--keep-metrics', result.stdout)

    def test_cpu_and_memory_queries_select_only_runtime_board(self):
        with mock.patch.object(prometheus_client, "PrometheusClient") as client:
            client.return_value.query.return_value = [{"value": [0, "12.5"]}]
            values = prometheus_client.get_node_exporter_metrics(
                "http://localhost:9090", board="spacemit-k3")
        self.assertEqual(values, {"cpu_percent": 12.5, "memory_percent": 12.5})
        queries = [call.args[0] for call in client.return_value.query.call_args_list]
        self.assertEqual(len(queries), 2)
        for query in queries:
            self.assertIn('board="spacemit-k3"', query)

    def test_endpoint_exposes_group_integrity_and_receive_time(self):
        store = metrics_server.MetricsStorage()
        store.update_session("123")
        with mock.patch.object(metrics_server.time, "time", return_value=1000):
            store.add_group({
                "board": "spacemit-k3", "kernel": "test", "stress": "off",
                "group_index": 4, "requests_sent": 20,
                "responses_received": 19, "timeouts": 1,
                "mean_latency_us": 25, "avg_latency_us": 45,
            })
        handler = object.__new__(metrics_server.PrometheusMetricsHandler)
        handler.storage = store
        body = handler.generate_metrics()
        labels = 'board="spacemit-k3",kernel="test",session_id="123",stress="off"'
        self.assertIn(f'arduino_group_requests_sent{{{labels}}} 20', body)
        self.assertIn(f'arduino_group_responses_received{{{labels}}} 19', body)
        self.assertIn(f'arduino_group_timeouts{{{labels}}} 1', body)
        self.assertIn(f'arduino_group_index{{{labels}}} 4', body)
        self.assertIn(f'arduino_last_group_timestamp_seconds{{{labels}}} 1000', body)
        self.assertIn(f'arduino_latency_mean{{{labels}}} 25', body)


if __name__ == "__main__":
    unittest.main()
