#!/usr/bin/env python3
"""
PromQL-backed equivalents of SQLite query functions from plot_statistics.py.

Instead of reading from arduino_data.db, these functions query a Prometheus
server and return pandas DataFrames / dicts with the same structure.

Usage:
    from promql_metrics import get_session_info, get_latency_stats, \
        get_soc_metrics, list_sessions

    client = PrometheusClient("http://localhost:9090")
    info = get_session_info(client, session_id=123456)
    df   = get_latency_stats(client, session_id=123456, top_n=75)
    soc  = get_soc_metrics(client, session_id=123456)
    list_sessions(client)
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, List, Dict, Any

from prometheus_client import PrometheusClient


def _range_to_df(result: List[Dict], value_name: str) -> Optional[pd.DataFrame]:
    """Convert a Prometheus query_range result into a DataFrame.

    Each time series becomes one column (named by its group label),
    with timestamps as the index.
    """
    if not result:
        return None

    all_series = {}
    for r in result:
        group = r.get("metric", {}).get("group", "0")
        values = r.get("values", [])
        if not values:
            continue
        ts_vals = {float(t): float(v) for t, v in values}
        all_series[f"{value_name}_{group}"] = ts_vals

    if not all_series:
        return None

    df = pd.DataFrame(all_series)
    df.index.name = "timestamp"
    df.index = pd.to_datetime(df.index, unit="s")
    return df.sort_index()


def _instant_scalar(results: List[Dict]) -> Optional[float]:
    """Extract a scalar value from an instant query result."""
    if not results:
        return None
    val = results[0].get("value", [0, 0])[1]
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _instant_labels(results: List[Dict]) -> List[Dict]:
    """Extract label sets + values from an instant query."""
    out = []
    for r in results:
        labels = r.get("metric", {})
        val = r.get("value", [0, 0])[1]
        try:
            val = float(val)
        except (ValueError, TypeError):
            val = 0.0
        labels["_value"] = val
        out.append(labels)
    return out


def get_session_info(client: PrometheusClient, session_id: int,
                     threshold_us: int = 75) -> Optional[dict]:
    """Get session metadata from Prometheus.

    Returns dict with same keys as the SQLite version, or None.
    Falls/recoveries and exceed counts are 0 (not in Prometheus).
    """
    sid = str(session_id)
    filters = f'session_id="{sid}"'

    # Check session exists
    exists = client.query(f'arduino_session_info{{{filters}}}')
    if not exists or float(exists[0].get("value", [0, 0])[1]) == 0:
        return None

    labels = exists[0].get("metric", {})

    # Group count
    groups_result = client.query(f'count(arduino_latency_avg{{{filters}}})')
    groups_count = int(_instant_scalar(groups_result) or 0)

    # Average jitter
    jitter_result = client.query(f'avg(arduino_jitter{{{filters}}})')
    avg_jitter = _instant_scalar(jitter_result) or 0.0

    # Worst count (session-level, no group label)
    wc_filter = f'board="{labels.get("board","unknown")}",kernel="{labels.get("kernel","unknown")}",session_id="{sid}"'
    wc_result = client.query(f'arduino_worst_count{{{wc_filter}}}')
    worst_count = int(_instant_scalar(wc_result) or 125)

    # Interval and measurements per group (from first group's metadata)
    # These aren't stored in Prometheus, use defaults
    interval_us = 300
    measurements_per_group = 1500

    # Time range from latency data
    range_result = client.query_range(
        f'arduino_latency_avg{{{filters}}}',
        start=0, end=int(datetime.now().timestamp()),
        step="1h"
    )
    start_time = ""
    end_time = ""
    if range_result and range_result.get("result"):
        values = range_result["result"][0].get("values", [])
        if values:
            start_ts = int(float(values[0][0]))
            end_ts = int(float(values[-1][0]))
            start_time = datetime.fromtimestamp(start_ts).isoformat()
            end_time = datetime.fromtimestamp(end_ts).isoformat()

    # SoC metrics averages
    avg_cpu = _instant_scalar(client.query(f'avg(soc_cpu_percent{{{filters}}})'))
    avg_mem = _instant_scalar(client.query(f'avg(soc_memory_percent{{{filters}}})'))

    return {
        "session_id": session_id,
        "start_time": start_time,
        "end_time": end_time,
        "target_board": labels.get("board", "unknown"),
        "target_kernel": labels.get("kernel", "unknown"),
        "target_stress": labels.get("stress", "off"),
        "groups_count": groups_count,
        "avg_jitter": avg_jitter,
        "interval_us": interval_us,
        "measurements_per_group": measurements_per_group,
        "worst_count": worst_count,
        "falls_count": 0,           # not in Prometheus
        "total_exceeds": 0,         # not in Prometheus
        "groups_with_exceeds": 0,   # not in Prometheus
        "max_exceed": 0,            # not in Prometheus
        "avg_cpu": avg_cpu,
        "avg_mem": avg_mem,
        "max_cpu": None,
        "max_mem": None,
    }


def get_latency_stats(client: PrometheusClient, session_id: int = None,
                      top_n: int = 125,
                      threshold_us: int = 75) -> Optional[pd.DataFrame]:
    """Get latency time series from Prometheus as a DataFrame.

    Matches the SQLite version's column structure.
    """
    sid = str(session_id)
    filters = f'session_id="{sid}"'

    now = int(datetime.now().timestamp())

    # Query session time range first
    meta = client.query(f'arduino_session_info{{{filters}}}')
    if not meta:
        return None

    # Use a reasonable time window (last 24 hours or from session start)
    start = now - 86400

    def _query_metric(metric_name):
        raw = client.query_range(
            f'{metric_name}{{{filters}}}',
            start=start, end=now, step="1s"
        )
        if not raw or not raw.get("result"):
            return None
        return _range_to_df(raw["result"], metric_name)

    avg_df = _query_metric("arduino_latency_avg")
    max_df = _query_metric("arduino_latency_max")
    jitter_df = _query_metric("arduino_jitter")

    if avg_df is None or avg_df.empty:
        return None

    # Build a unified DataFrame from all group-labeled columns
    records = []
    for col in avg_df.columns:
        group_str = col.replace("arduino_latency_avg_", "")
        group_idx = int(group_str) if group_str.isdigit() else None
        if group_idx is None:
            continue

        series_avg = avg_df[col].dropna()
        series_max = max_df[f"arduino_latency_max_{group_str}"].dropna() if max_df is not None else None
        series_jit = jitter_df[f"arduino_jitter_{group_str}"].dropna() if jitter_df is not None else None

        if series_avg.empty:
            continue

        avg_val = series_avg.iloc[0]
        max_val = float(series_max.iloc[0]) if series_max is not None and not series_max.empty else avg_val
        jit_val = float(series_jit.iloc[0]) if series_jit is not None and not series_jit.empty else 0.0
        exceeds = 1 if max_val > threshold_us else 0

        records.append({
            "group_index": group_idx,
            "avg_latency_us": avg_val,
            "min_latency_us": avg_val,     # min not stored in Prometheus
            "max_latency_us": max_val,
            "latencies_used": top_n,
            "jitter_us": jit_val,
            "exceeds_threshold_count": exceeds,
            "exceeds_threshold_percent": (exceeds / max(top_n, 1)) * 100,
        })

    if not records:
        return None

    df = pd.DataFrame(records).sort_values("group_index")
    return df


def get_soc_metrics(client: PrometheusClient, session_id: int = None) -> Optional[pd.DataFrame]:
    """Get SoC CPU/memory time series from Prometheus as a DataFrame.

    Matches the SQLite version's column structure.
    """
    sid = str(session_id)
    filters = f'session_id="{sid}"'

    now = int(datetime.now().timestamp())
    start = now - 86400

    cpu_df = _range_to_df(
        client.query_range(f'soc_cpu_percent{{{filters}}}', start=start, end=now, step="1s").get("result", []),
        "cpu"
    )
    mem_df = _range_to_df(
        client.query_range(f'soc_memory_percent{{{filters}}}', start=start, end=now, step="1s").get("result", []),
        "mem"
    )

    if cpu_df is None or cpu_df.empty:
        return None

    records = []
    for col in cpu_df.columns:
        group_str = col.replace("cpu_", "")
        group_idx = int(group_str) if group_str.isdigit() else None
        if group_idx is None:
            continue

        cpu_series = cpu_df[col].dropna()
        mem_series = mem_df[f"mem_{group_str}"].dropna() if mem_df is not None else None

        if cpu_series.empty:
            continue

        cpu_val = float(cpu_series.iloc[0])
        mem_val = float(mem_series.iloc[0]) if mem_series is not None and not mem_series.empty else 0.0

        records.append({
            "session_id": session_id,
            "group_index": group_idx,
            "cpu_percent": cpu_val,
            "memory_percent": mem_val,
            "cpu_max": cpu_val,
            "mem_max": mem_val,
            "cpu_avg": cpu_val,
            "mem_avg": mem_val,
            "samples_in_group": 1500,
            "duration_ms": 0.0,
        })

    if not records:
        return None

    return pd.DataFrame(records).sort_values("group_index")


def list_sessions(client: PrometheusClient,
                  threshold_us: int = 75) -> None:
    """Print session list from Prometheus data (same format as SQLite version)."""
    results = client.query('arduino_session_info')

    if not results:
        print("No sessions found in Prometheus")
        return

    # Header
    print(f"{'Session':<10} {'Board':<12} {'Kernel':<18} {'Stress':<7} "
          f"{'Groups':<8} {'Interval':<9} {'Worst':<7} {'Avg Lat':<10} "
          f"{'Avg Jit':<10} {'Exceeds':<8} {'Avg CPU':<8} {'Avg MEM':<8} "
          f"{'Falls':<6} {'First Seen'}")
    print("-" * 160)

    for r in results:
        labels = r.get("metric", {})
        session_id = labels.get("session_id", "?")
        board = labels.get("board", "?")
        kernel = labels.get("kernel", "?")
        stress = labels.get("stress", "off")

        sid = session_id
        filters = f'session_id="{sid}",board="{board}"'

        groups = int(_instant_scalar(client.query(f'count(arduino_latency_avg{{{filters}}}')) or 0)
        avg_lat = _instant_scalar(client.query(f'avg(arduino_latency_avg{{{filters}}})'))
        avg_jit = _instant_scalar(client.query(f'avg(arduino_jitter{{{filters}}})'))
        avg_cpu_val = _instant_scalar(client.query(f'avg(soc_cpu_percent{{{filters}}})'))
        avg_mem_val = _instant_scalar(client.query(f'avg(soc_memory_percent{{{filters}}})'))

        wc = int(_instant_scalar(client.query(f'arduino_worst_count{{board="{board}",kernel="{kernel}",session_id="{sid}"}}')) or 125)

        lat_str = f"{avg_lat:.2f}" if avg_lat else "N/A"
        jit_str = f"{avg_jit:.2f}" if avg_jit else "N/A"
        cpu_str = f"{avg_cpu_val:.2f}" if avg_cpu_val else "N/A"
        mem_str = f"{avg_mem_val:.2f}" if avg_mem_val else "N/A"

        print(f"{sid:<10} {board:<12} {kernel:<18} {stress:<7} "
              f"{groups:<8} {'300':<9} {wc:<7} {lat_str:<10} "
              f"{jit_str:<10} {'0':<8} {cpu_str:<8} {mem_str:<8} "
              f"{'0':<6} {'-'}")

    print("-" * 160)
    print(f"Total sessions: {len(results)}")
