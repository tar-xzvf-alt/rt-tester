#!/usr/bin/env python3
"""
Prometheus Client Module

Queries metrics from Prometheus server instead of SQLite database.
"""

import requests
from typing import Optional, List, Dict, Any
import time
from datetime import datetime


class PrometheusClient:
    """Client for querying Prometheus HTTP API."""
    
    def __init__(self, prometheus_url: str = "http://localhost:9090", timeout: int = 30):
        """
        Initialize Prometheus client.
        
        Args:
            prometheus_url: Prometheus server URL
            timeout: Request timeout in seconds
        """
        self.prometheus_url = prometheus_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
    
    def query(self, query: str) -> List[Dict[str, Any]]:
        """
        Execute instant query.
        
        Args:
            query: PromQL query string
            
        Returns:
            List of result dictionaries
        """
        try:
            response = self.session.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query},
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") != "success":
                raise ValueError(f"Query failed: {data.get('error', 'Unknown error')}")
            
            return data.get("data", {}).get("result", [])
            
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to query Prometheus: {e}")
    
    def query_range(self, query: str, start: int, end: int, step: str = "15s") -> Dict[str, Any]:
        """
        Execute range query for time series data.
        
        Args:
            query: PromQL query string
            start: Start timestamp (Unix epoch seconds)
            end: End timestamp (Unix epoch seconds)
            step: Query resolution step (e.g., "15s", "1m")
            
        Returns:
            Dictionary with time series data
        """
        try:
            response = self.session.get(
                f"{self.prometheus_url}/api/v1/query_range",
                params={
                    "query": query,
                    "start": start,
                    "end": end,
                    "step": step
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") != "success":
                raise ValueError(f"Query failed: {data.get('error', 'Unknown error')}")
            
            return data.get("data", {})
            
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to query Prometheus: {e}")
    
    def get_soc_metrics(self, board: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get SoC CPU and memory metrics.
        
        Args:
            board: Board name (label value)
            session_id: Optional session ID filter
            
        Returns:
            Dictionary with latest metrics
        """
        labels = f'board="{board}"'
        if session_id:
            labels += f',session_id="{session_id}"'
        
        cpu_query = f"soc_cpu_percent{{{labels}}}"
        mem_query = f"soc_memory_percent{{{labels}}}"
        
        results = {}
        
        for metric_name, query in [("cpu", cpu_query), ("memory", mem_query)]:
            try:
                result = self.query(query)
                if result:
                    latest = result[-1]
                    results[metric_name] = {
                        "value": float(latest.get("value", [0, 0])[1]),
                        "timestamp": latest.get("value", [0, 0])[0]
                    }
            except Exception:
                results[metric_name] = {"value": None, "timestamp": None}
        
        return results
    
    def get_latency_metrics(self, board: str, session_id: str, 
                            group: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get Arduino latency metrics.
        
        Args:
            board: Board name
            session_id: Session ID
            group: Optional group index filter
            
        Returns:
            List of latency measurements
        """
        labels = f'board="{board}",session_id="{session_id}"'
        if group is not None:
            labels += f',group="{group}"'
        
        avg_query = f"arduino_latency_avg{{{labels}}}"
        worst_query = f"arduino_latency_worst{{{labels}}}"
        jitter_query = f"arduino_jitter{{{labels}}}"
        
        results = []
        
        try:
            avg_results = self.query(avg_query)
            worst_results = self.query(worst_query)
            jitter_results = self.query(jitter_query)
            
            for avg in avg_results:
                metric = {
                    "group": int(avg.get("metric", {}).get("group", 0)),
                    "latency_avg": float(avg.get("value", [0, 0])[1]),
                    "timestamp": avg.get("value", [0, 0])[0]
                }
                
                for w in worst_results:
                    if w.get("metric", {}).get("group") == avg.get("metric", {}).get("group"):
                        metric["latency_worst"] = float(w.get("value", [0, 0])[1])
                        break
                
                for j in jitter_results:
                    if j.get("metric", {}).get("group") == avg.get("metric", {}).get("group"):
                        metric["jitter"] = float(j.get("value", [0, 0])[1])
                        break
                
                results.append(metric)
                
        except Exception as e:
            print(f"Warning: Failed to get latency metrics: {e}")
        
        return results
    
    def get_all_sessions(self, board: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all session IDs.
        
        Args:
            board: Optional board filter
            
        Returns:
            List of session dictionaries
        """
        query = 'arduino_latency_avg'
        if board:
            query = f'{query}{{board="{board}"}}'
        
        try:
            results = self.query(query)
            sessions = set()
            for r in results:
                labels = r.get("metric", {})
                sessions.add(labels.get("session_id"))
            
            return [{"session_id": s} for s in sorted(sessions) if s]
        except Exception:
            return []
    
    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """
        Get summary statistics for a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            Dictionary with summary stats
        """
        summary = {
            "session_id": session_id,
            "groups_count": 0,
            "latency_avg_avg": 0,
            "latency_worst_max": 0,
            "jitter_avg": 0
        }
        
        queries = [
            ("groups", "count(arduino_latency_avg{session_id=\"%s\"})" % session_id),
            ("latency_avg", "avg(arduino_latency_avg{session_id=\"%s\"})" % session_id),
            ("latency_worst", "max(arduino_latency_worst{session_id=\"%s\"})" % session_id),
            ("jitter", "avg(arduino_jitter{session_id=\"%s\"})" % session_id),
        ]
        
        for key, query in queries:
            try:
                result = self.query(query)
                if result:
                    summary[key] = float(result[0].get("value", [0, 0])[1])
            except Exception:
                pass
        
        return summary
    
    def health_check(self) -> bool:
        """
        Check if Prometheus server is reachable.
        
        Returns:
            True if healthy
        """
        try:
            response = self.session.get(
                f"{self.prometheus_url}/-/healthy",
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False


def get_prometheus_client(config: Optional[Dict] = None) -> PrometheusClient:
    """
    Factory function to create PrometheusClient from config.
    
    Args:
        config: Optional configuration dictionary with 'prometheus_url'
        
    Returns:
        PrometheusClient instance
    """
    url = "http://localhost:9090"
    if config and 'prometheus' in config:
        url = config['prometheus'].get('url', url)
    return PrometheusClient(prometheus_url=url)