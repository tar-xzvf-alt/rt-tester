#!/usr/bin/env python3
"""
Simple HTTP metrics server for Prometheus to scrape

This module provides a lightweight HTTP server that exposes latency metrics
from Arduino in Prometheus format. Prometheus scrapes this endpoint.

Groups are buffered between scrapes and returned with timestamps
so no data is lost. After a session ends, Prometheus retains the full
history (within retention limits), enabling long-term dashboards.

Usage:
    python3 metrics_server.py [--port 9101]
"""

import http.server
import socketserver
import threading
import time
from typing import Dict, List, Optional


class MetricsStorage:
    """Thread-safe storage for latency metrics."""

    def __init__(self):
        self._lock = threading.RLock()
        self._current_session_id: Optional[str] = None
        self._pending_groups: List[tuple] = []  # (timestamp_sec, group_data)
        self._max_pending = 10000

    def update_session(self, session_id: str):
        with self._lock:
            self._current_session_id = session_id
            self._pending_groups.clear()

    def add_group(self, group_data: Dict):
        with self._lock:
            if self._current_session_id:
                group_data['session_id'] = self._current_session_id
                self._pending_groups.append((time.time(), group_data))
                if len(self._pending_groups) > self._max_pending:
                    self._pending_groups = self._pending_groups[-self._max_pending:]

    def get_and_clear_pending(self) -> List[tuple]:
        """Get all pending groups and clear the buffer."""
        with self._lock:
            pending = self._pending_groups
            self._pending_groups = []
            return pending


class PrometheusMetricsHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for /metrics endpoint."""

    storage: MetricsStorage = None

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def do_GET(self):
        if self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
            self.end_headers()

            metrics_output = self.generate_metrics()
            self.wfile.write(metrics_output.encode('utf-8'))
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()

    def generate_metrics(self) -> str:
        """Generate Prometheus metrics output for all pending groups."""
        pending = self.storage.get_and_clear_pending()
        if not pending:
            return ""

        # Session-level labels from the first group
        _, first = pending[0]
        session_id = str(first.get('session_id', 'unknown'))
        board = first.get('board', 'unknown')
        kernel = first.get('kernel', 'unknown')
        stress = first.get('stress', 'off')

        label_base = f'board="{board}",kernel="{kernel}",session_id="{session_id}",stress="{stress}"'

        lines = []

        # TYPE declarations (once per scrape)
        lines.append("# TYPE arduino_latency_avg gauge")
        lines.append("# TYPE arduino_latency_mean gauge")
        lines.append("# TYPE arduino_latency_min gauge")
        lines.append("# TYPE arduino_latency_max gauge")
        lines.append("# TYPE arduino_jitter gauge")
        lines.append("# TYPE soc_cpu_percent gauge")
        lines.append("# TYPE soc_memory_percent gauge")

        for ts, group in pending:
            timestamp_ms = int(ts * 1000)
            group_idx = group.get('group_index', 0)

            lines.append(f'arduino_latency_avg{{group="{group_idx}",{label_base}}} {group.get("avg_latency_us", 0)} {timestamp_ms}')
            lines.append(f'arduino_latency_mean{{group="{group_idx}",{label_base}}} {group.get("mean_latency_us", 0)} {timestamp_ms}')
            lines.append(f'arduino_latency_min{{group="{group_idx}",{label_base}}} {group.get("min_latency_us", 0)} {timestamp_ms}')
            lines.append(f'arduino_latency_max{{group="{group_idx}",{label_base}}} {group.get("max_latency_us", 0)} {timestamp_ms}')
            lines.append(f'arduino_jitter{{group="{group_idx}",{label_base}}} {group.get("jitter_us", 0)} {timestamp_ms}')

            soc_cpu = group.get('soc_cpu_percent')
            if soc_cpu is not None:
                lines.append(f'soc_cpu_percent{{group="{group_idx}",board="{board}",session_id="{session_id}"}} {soc_cpu:.2f} {timestamp_ms}')
            soc_mem = group.get('soc_memory_percent')
            if soc_mem is not None:
                lines.append(f'soc_memory_percent{{group="{group_idx}",board="{board}",session_id="{session_id}"}} {soc_mem:.2f} {timestamp_ms}')

        # Session-level info (once per scrape)
        worst_count = first.get('worst_count', 0)
        lines.append(f"# TYPE arduino_worst_count gauge")
        lines.append(f'arduino_worst_count{{board="{board}",kernel="{kernel}",session_id="{session_id}"}} {worst_count}')
        lines.append(f"# TYPE arduino_session_info gauge")
        lines.append(f'arduino_session_info{{{label_base}}} 1')

        return "\n".join(lines)


class ReuseTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


class MetricsServer:
    """HTTP server for Prometheus metrics."""

    def __init__(self, port: int = 9101):
        self.port = port
        self.storage = MetricsStorage()
        self.server = None
        self.thread = None

    def start(self):
        """Start the metrics HTTP server."""
        PrometheusMetricsHandler.storage = self.storage

        self.server = ReuseTCPServer(("", self.port), PrometheusMetricsHandler)

        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        print(f"Metrics server started on http://0.0.0.0:{self.port}/metrics")
        print(f"Health check: http://0.0.0.0:{self.port}/health")

    def stop(self):
        """Stop the metrics HTTP server."""
        if self.server:
            self.server.shutdown()
            print("Metrics server stopped")

    def update_session(self, session_id: str):
        """Update current session ID."""
        self.storage.update_session(session_id)

    def add_group(self, group_data: Dict):
        """Add a new group of latency measurements."""
        self.storage.add_group(group_data)


def run_server(port: int = 9101):
    """Run standalone metrics server."""
    server = MetricsServer(port)
    server.start()

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Prometheus metrics server')
    parser.add_argument('--port', type=int, default=9101, help='Port to listen on')
    args = parser.parse_args()

    run_server(args.port)
