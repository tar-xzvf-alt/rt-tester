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
    
    def update_session(self, session_id: str):
        with self._lock:
            self._current_session_id = session_id
            self._latest_group = None
    
    def add_group(self, group_data: Dict):
        with self._lock:
            if self._current_session_id:
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
        group_index = latest.get('group_index', 0)
        
        mean_latency = latest.get('mean_latency_us', 0)
        avg_latency = latest.get('avg_latency_us', 0)
        min_latency = latest.get('min_latency_us', 0)
        max_latency = latest.get('max_latency_us', 0)
        jitter = latest.get('jitter_us', 0)
        worst_count = latest.get('worst_count', 0)
        
        lines.append(f"# TYPE arduino_latency_avg gauge")
        lines.append(f'arduino_latency_avg{{board="{board}",kernel="{kernel}",session_id="{session_id}",stress="{stress}",group="{group_index}"}} {avg_latency}')
        
        lines.append(f"# TYPE arduino_latency_mean gauge")
        lines.append(f'arduino_latency_mean{{board="{board}",kernel="{kernel}",session_id="{session_id}",stress="{stress}",group="{group_index}"}} {mean_latency}')
        
        lines.append(f"# TYPE arduino_latency_min gauge")
        lines.append(f'arduino_latency_min{{board="{board}",kernel="{kernel}",session_id="{session_id}",stress="{stress}",group="{group_index}"}} {min_latency}')
        
        lines.append(f"# TYPE arduino_latency_max gauge")
        lines.append(f'arduino_latency_max{{board="{board}",kernel="{kernel}",session_id="{session_id}",stress="{stress}",group="{group_index}"}} {max_latency}')
        
        lines.append(f"# TYPE arduino_jitter gauge")
        lines.append(f'arduino_jitter{{board="{board}",kernel="{kernel}",session_id="{session_id}",stress="{stress}",group="{group_index}"}} {jitter}')
        
        lines.append(f"# TYPE arduino_worst_count gauge")
        lines.append(f'arduino_worst_count{{board="{board}",kernel="{kernel}",session_id="{session_id}"}} {worst_count}')
        
        worst_latencies = latest.get('worst_latencies_us', [])
        if worst_latencies:
            for i, lat in enumerate(worst_latencies[:25]):
                lines.append(f"# TYPE arduino_latency_worst_{i+1} gauge")
                lines.append(f'arduino_latency_worst_{i+1}{{board="{board}",kernel="{kernel}",session_id="{session_id}",stress="{stress}",group="{group_index}"}} {lat}')
        
        lines.append(f"# TYPE arduino_session_info gauge")
        lines.append(f'arduino_session_info{{board="{board}",kernel="{kernel}",session_id="{session_id}",stress="{stress}"}} 1')
        
        return "\n".join(lines)


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
        
        self.server = socketserver.TCPServer(("", self.port), PrometheusMetricsHandler)
        self.server.allow_reuse_address = True
        
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