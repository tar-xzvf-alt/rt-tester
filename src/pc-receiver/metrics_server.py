#!/usr/bin/env python3
"""
Simple HTTP metrics server for Prometheus to scrape

This module provides a lightweight HTTP server that exposes latency metrics
from Arduino in Prometheus format. Prometheus scrapes this endpoint.

Usage:
    python3 metrics_server.py [--port 9101]
"""

import http.server
import socketserver
import threading
import json
import time
from typing import Dict, List, Optional
from datetime import datetime


class MetricsStorage:
    """Thread-safe storage for latency metrics."""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._current_session_id: Optional[str] = None
        self._latest_group: Optional[Dict] = None
        self._groups_history: List[Dict] = []
        self._max_history = 10000  # Keep last 10000 groups
        self._seen_groups = set()
        self._session_totals = {'requests_sent': 0, 'responses_received': 0, 'timeouts': 0}
    
    def update_session(self, session_id: str):
        with self._lock:
            self._current_session_id = session_id
            self._latest_group = None
            self._seen_groups.clear()
            self._session_totals = dict.fromkeys(self._session_totals, 0)
    
    def add_group(self, group_data: Dict):
        with self._lock:
            if self._current_session_id:
                group_data = dict(group_data)
                index = group_data.get('group_index')
                if index is not None and index in self._seen_groups:
                    return
                if index is not None:
                    self._seen_groups.add(index)
                if all(field in group_data for field in self._session_totals):
                    for field in self._session_totals:
                        self._session_totals[field] += int(group_data[field])
                    group_data['session_totals'] = dict(self._session_totals)
                group_data.setdefault('received_timestamp_seconds', time.time())
                group_data['session_id'] = self._current_session_id
                self._groups_history.append(group_data)
                
                if len(self._groups_history) > self._max_history:
                    self._groups_history = self._groups_history[-self._max_history:]
                
                self._latest_group = group_data
    
    def get_latest_group(self) -> Optional[Dict]:
        with self._lock:
            return self._latest_group
    
    def get_all_groups(self) -> List[Dict]:
        with self._lock:
            return self._groups_history.copy()


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
        """Generate Prometheus metrics output."""
        lines = []
        latest = self.storage.get_latest_group()
        
        if not latest:
            return ""
        
        session_id = latest.get('session_id', 'unknown')
        board = latest.get('board', 'unknown')
        kernel = latest.get('kernel', 'unknown')
        stress = latest.get('stress', 'off')
        
        mean_latency = latest.get('mean_latency_us', 0)
        avg_latency = latest.get('avg_latency_us', 0)
        min_latency = latest.get('min_latency_us', 0)
        max_latency = latest.get('max_latency_us', 0)
        jitter = latest.get('jitter_us', 0)
        worst_count = latest.get('worst_count', 0)
        
        labels = f'board="{board}",kernel="{kernel}",session_id="{session_id}",stress="{stress}"'
        
        lines.append(f"# TYPE arduino_latency_avg gauge")
        lines.append(f'arduino_latency_avg{{{labels}}} {avg_latency}')
        
        lines.append(f"# TYPE arduino_latency_mean gauge")
        lines.append(f'arduino_latency_mean{{{labels}}} {mean_latency}')
        
        lines.append(f"# TYPE arduino_latency_min gauge")
        lines.append(f'arduino_latency_min{{{labels}}} {min_latency}')
        
        lines.append(f"# TYPE arduino_latency_max gauge")
        lines.append(f'arduino_latency_max{{{labels}}} {max_latency}')
        
        lines.append(f"# TYPE arduino_jitter gauge")
        lines.append(f'arduino_jitter{{{labels}}} {jitter}')
        
        lines.append(f"# TYPE arduino_worst_count gauge")
        lines.append(f'arduino_worst_count{{board="{board}",kernel="{kernel}",session_id="{session_id}"}} {worst_count}')
        
        worst_latencies = latest.get('worst_latencies_us', [])
        if worst_latencies:
            for i, lat in enumerate(worst_latencies[:25]):
                lines.append(f"# TYPE arduino_latency_worst_{i+1} gauge")
                lines.append(f'arduino_latency_worst_{i+1}{{{labels}}} {lat}')
        
        lines.append(f"# TYPE arduino_session_info gauge")
        lines.append(f'arduino_session_info{{board="{board}",kernel="{kernel}",session_id="{session_id}",stress="{stress}"}} 1')

        # Latest-group gauges, not cumulative counters. Receipt time lets a
        # dashboard distinguish a retained last result from active collection.
        for field in ('group_index', 'requests_sent', 'responses_received', 'timeouts'):
            if field in latest:
                name = 'arduino_group_index' if field == 'group_index' else f'arduino_group_{field}'
                lines.append(f'# TYPE {name} gauge')
                lines.append(f'{name}{{{labels}}} {int(latest[field])}')
        lines.append('# TYPE arduino_last_group_timestamp_seconds gauge')
        lines.append(
            f'arduino_last_group_timestamp_seconds{{{labels}}} '
            f'{latest["received_timestamp_seconds"]}'
        )
        for field, value in latest.get('session_totals', {}).items():
            name = {
                'requests_sent': 'arduino_requests_total',
                'responses_received': 'arduino_responses_total',
                'timeouts': 'arduino_timeouts_total',
            }[field]
            lines.append(f'# TYPE {name} counter')
            lines.append(f'{name}{{{labels}}} {value}')
        
        # Add CPU/memory metrics from node_exporter (if available)
        soc_cpu = latest.get('soc_cpu_percent')
        soc_mem = latest.get('soc_memory_percent')
        if soc_cpu is not None:
            lines.append(f"# TYPE soc_cpu_percent gauge")
            lines.append(f'soc_cpu_percent{{board="{board}",session_id="{session_id}"}} {soc_cpu:.2f}')
        if soc_mem is not None:
            lines.append(f"# TYPE soc_memory_percent gauge")
            lines.append(f'soc_memory_percent{{board="{board}",session_id="{session_id}"}} {soc_mem:.2f}')
        
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
