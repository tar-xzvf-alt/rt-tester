#!/usr/bin/env python3
"""
Arduino Data Visualization Tool with SoC Metrics

This script provides visualization and analysis tools for data collected from Arduino
measurement system, including SoC (target device) metrics like CPU and memory usage.
"""

import sqlite3
import argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import pandas as pd
import numpy as np
import os
from datetime import datetime
import logging
import re

# Default threshold in microseconds
DEFAULT_THRESHOLD_US = 250


def setup_session_logging(session_id: int, log_dir: str = "logs") -> logging.Logger:
    """Set up a separate log file for a specific session."""
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(f"session_{session_id}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    log_file = os.path.join(log_dir, f"session_{session_id}.log")
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def sanitize_filename(text: str) -> str:
    """Sanitize text for use in filename."""
    sanitized = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', text)
    sanitized = re.sub(r'_+', '_', sanitized)
    sanitized = sanitized.strip('_')
    return sanitized


def get_latency_stats(db_path: str, session_id: int = None, top_n: int = 125,
                      threshold_us: int = DEFAULT_THRESHOLD_US) -> pd.DataFrame:
    """
    Calculate statistics for the worst N latencies in each group.
    Also count how many latencies exceed threshold in each group.
    """

    conn = sqlite3.connect(db_path)

    # Get all latencies for the session
    query = '''
        SELECT
            g.session_id,
            g.group_index,
            g.jitter_us,
            g.target_board,
            g.target_kernel,
            g.target_stress,
            g.target_payload,
            l.latency_us,
            l.rank_in_group
        FROM groups g
        JOIN latencies l ON g.id = l.group_id
    '''
    params = []

    if session_id is not None:
        query += ' WHERE g.session_id = ? AND l.rank_in_group <= ?'
        params.extend([session_id, top_n])
    else:
        query += ' WHERE l.rank_in_group <= ?'
        params.append(top_n)

    query += ' ORDER BY g.group_index, l.rank_in_group'

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if df.empty:
        return None

    # Calculate statistics per group
    stats = df.groupby('group_index').agg({
        'latency_us': ['mean', 'min', 'max', 'count'],
        'jitter_us': 'first',
        'target_board': 'first',
        'target_kernel': 'first',
        'target_stress': 'first',
        'target_payload': 'first'
    }).reset_index()

    stats.columns = ['group_index', 'avg_latency_us', 'min_latency_us',
                     'max_latency_us', 'latencies_used', 'jitter_us',
                     'target_board', 'target_kernel', 'target_stress',
                     'target_payload']

    # Count how many latencies exceed threshold in each group
    df['exceeds_threshold'] = df['latency_us'] > threshold_us
    exceed_counts = df.groupby('group_index')['exceeds_threshold'].sum().reset_index()
    exceed_counts.columns = ['group_index', 'exceeds_threshold_count']

    # Merge with stats
    stats = pd.merge(stats, exceed_counts, on='group_index', how='left')
    stats['exceeds_threshold_count'] = stats['exceeds_threshold_count'].fillna(0).astype(int)

    # Calculate percentage of measurements exceeding threshold
    stats['exceeds_threshold_percent'] = (stats['exceeds_threshold_count'] / stats['latencies_used']) * 100

    return stats


def get_soc_metrics(db_path: str, session_id: int = None) -> pd.DataFrame:
    """Get SoC (target device) metrics from database."""
    conn = sqlite3.connect(db_path)

    query = '''
        SELECT
            session_id,
            group_index,
            cpu_percent,
            memory_percent,
            cpu_max,
            mem_max,
            cpu_avg,
            mem_avg,
            samples_in_group,
            duration_ms
        FROM soc_metrics
    '''
    params = []

    if session_id is not None:
        query += ' WHERE session_id = ?'
        params.append(session_id)

    query += ' ORDER BY group_index'

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    return df if not df.empty else None


def get_trace_metrics(db_path: str, session_id: int = None) -> pd.DataFrame:
    """Get trace stage metrics from database."""
    conn = sqlite3.connect(db_path)
    query = '''
        SELECT
            session_id,
            group_index,
            host,
            stage,
            count,
            min_us,
            avg_us,
            max_us
        FROM trace_group_metrics
    '''
    params = []
    if session_id is not None:
        query += ' WHERE session_id = ?'
        params.append(session_id)
    query += ' ORDER BY group_index, host, stage'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df if not df.empty else None


def get_events(db_path: str, session_id: int = None) -> pd.DataFrame:
    """Get system events from database."""
    conn = sqlite3.connect(db_path)
    query = '''
        SELECT
            id,
            session_id,
            event_type,
            event_time,
            event_time_us,
            time_since_start_us,
            group_index,
            details
        FROM events
    '''
    params = []
    if session_id is not None:
        query += ' WHERE session_id = ?'
        params.append(session_id)
    query += ' ORDER BY id'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df if not df.empty else None


def validate_session(db_path: str, session_id: int) -> dict:
    """Validate session data integrity. Returns dict of pass/fail checks."""
    result = {'passed': [], 'failed': [], 'warnings': []}
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Groups count
    groups = cur.execute('SELECT COUNT(*), MIN(group_index), MAX(group_index) FROM groups WHERE session_id=?', (session_id,)).fetchone()
    result['groups_count'] = groups[0]
    result['groups_min'] = groups[1]
    result['groups_max'] = groups[2]
    if groups[0] > 0:
        result['passed'].append(f'groups: {groups[0]} ({groups[1]}..{groups[2]})')
    else:
        result['failed'].append('no groups found')

    # Latencies count
    lat_count = cur.execute('SELECT COUNT(*) FROM latencies l JOIN groups g ON g.id=l.group_id WHERE g.session_id=?', (session_id,)).fetchone()[0]
    result['latencies_count'] = lat_count
    if lat_count > 0:
        result['passed'].append(f'latencies: {lat_count}')
    else:
        result['failed'].append('no latency measurements')

    # Latency / groups check
    worst = cur.execute('SELECT MIN(worst_count) FROM groups WHERE session_id=?', (session_id,)).fetchone()[0]
    expected_lat = groups[0] * (worst or 0)
    if expected_lat > 0 and lat_count != expected_lat:
        result['warnings'].append(f'latency count mismatch: got {lat_count}, expected ~{expected_lat} ({groups[0]} groups × {worst} worst)')

    # Trace metrics
    trace_count = cur.execute('SELECT COUNT(*) FROM trace_group_metrics WHERE session_id=?', (session_id,)).fetchone()[0]
    result['trace_count'] = trace_count
    if trace_count > 0:
        trace_hosts = cur.execute('SELECT host, COUNT(*) FROM trace_group_metrics WHERE session_id=? GROUP BY host', (session_id,)).fetchall()
        result['trace_hosts'] = dict(trace_hosts)
        trace_stages = cur.execute('SELECT DISTINCT stage FROM trace_group_metrics WHERE session_id=? ORDER BY stage', (session_id,)).fetchall()
        result['trace_stages'] = [s[0] for s in trace_stages]
        result['passed'].append(f'trace: {trace_count} rows, {len(trace_hosts)} hosts, {len(result["trace_stages"])} stages')
    else:
        result['warnings'].append('no trace metrics imported')

    # Events
    ev_types = cur.execute('SELECT event_type, COUNT(*) FROM events WHERE session_id=? GROUP BY event_type', (session_id,)).fetchall()
    result['events'] = dict(ev_types)
    if ev_types:
        result['passed'].append(f'events: {dict(ev_types)}')
        falls = cur.execute("SELECT COUNT(*) FROM events WHERE session_id=? AND event_type='fall'", (session_id,)).fetchone()[0]
        result['falls'] = falls
        if falls > 0:
            result['warnings'].append(f'session has {falls} fall(s)')

    # SoC metrics
    soc_count = cur.execute('SELECT COUNT(*) FROM soc_metrics WHERE session_id=?', (session_id,)).fetchone()[0]
    result['soc_count'] = soc_count
    if soc_count > 0:
        result['passed'].append(f'soc_metrics: {soc_count} rows')
    else:
        result['warnings'].append('no soc_metrics')

    conn.close()
    return result


def latest_session(db_path: str, stress: str = None) -> int | None:
    """Find the latest session ID, optionally filtered by stress status."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    if stress is not None:
        cur.execute('SELECT session_id FROM groups WHERE target_stress=? ORDER BY session_id DESC LIMIT 1', (stress,))
    else:
        cur.execute('SELECT session_id FROM groups ORDER BY session_id DESC LIMIT 1')
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None



def get_session_info(db_path: str, session_id: int, threshold_us: int = DEFAULT_THRESHOLD_US) -> dict:
    """Get detailed information about a specific session including threshold exceedances."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get session metadata from first group
    cursor.execute('''
        SELECT
            session_id,
            MIN(created_at) as start_time,
            MAX(created_at) as end_time,
            target_board,
            target_kernel,
            target_stress,
            target_payload,
            COUNT(*) as groups_count,
            AVG(jitter_us) as avg_jitter,
            MIN(delay_us) as interval_us,
            MIN(measurements_per_group) as measurements_per_group,
            MIN(worst_count) as worst_count
        FROM groups
        WHERE session_id = ?
        GROUP BY session_id
    ''', (session_id,))

    row = cursor.fetchone()

    if row:
        info = {
            'session_id': row[0],
            'start_time': row[1],
            'end_time': row[2],
            'target_board': row[3],
            'target_kernel': row[4],
            'target_stress': row[5] if row[5] else 'off',
            'target_payload': row[6] if row[6] else 'off',
            'groups_count': row[7],
            'avg_jitter': row[8],
            'interval_us': row[9],
            'measurements_per_group': row[10],
            'worst_count': row[11]
        }

        # Get fall events count
        cursor.execute('''
            SELECT COUNT(*) FROM events
            WHERE session_id = ? AND event_type = 'fall'
        ''', (session_id,))
        info['falls_count'] = cursor.fetchone()[0]

        # Get threshold exceedances statistics
        cursor.execute('''
            SELECT
                COUNT(l.id) as total_exceeds,
                COUNT(DISTINCT g.group_index) as groups_with_exceeds,
                MAX(l.latency_us) as max_exceed
            FROM groups g
            JOIN latencies l ON g.id = l.group_id
            WHERE g.session_id = ? AND l.latency_us > ?
        ''', (session_id, threshold_us))
        exceed_row = cursor.fetchone()

        if exceed_row:
            info['total_exceeds'] = exceed_row[0] if exceed_row[0] else 0
            info['groups_with_exceeds'] = exceed_row[1] if exceed_row[1] else 0
            info['max_exceed'] = exceed_row[2] if exceed_row[2] else 0

        # Get SoC metrics if available
        cursor.execute('''
            SELECT
                AVG(cpu_percent) as avg_cpu,
                AVG(memory_percent) as avg_mem,
                MAX(cpu_max) as max_cpu,
                MAX(mem_max) as max_mem
            FROM soc_metrics
            WHERE session_id = ?
        ''', (session_id,))
        soc_row = cursor.fetchone()

        if soc_row and soc_row[0] is not None:
            info['avg_cpu'] = soc_row[0]
            info['avg_mem'] = soc_row[1]
            info['max_cpu'] = soc_row[2]
            info['max_mem'] = soc_row[3]
        else:
            info['avg_cpu'] = None
            info['avg_mem'] = None
            info['max_cpu'] = None
            info['max_mem'] = None

    conn.close()
    return info if row else None


def plot_comprehensive_analysis(db_path: str, session_id: int = None,
                               output: str = None, top_n: int = 125,
                               threshold_us: int = DEFAULT_THRESHOLD_US) -> None:
    """
    Generate comprehensive plot with latency, jitter, and SoC metrics.
    Also shows threshold exceedances.
    """
    # Get all data
    latency_stats = get_latency_stats(db_path, session_id, top_n, threshold_us)
    soc_metrics = get_soc_metrics(db_path, session_id)

    if latency_stats is None or latency_stats.empty:
        print("No latency data to display")
        return

    # Get session info for title and filename
    session_info = None
    if session_id:
        session_info = get_session_info(db_path, session_id, threshold_us)

    if soc_metrics is None or soc_metrics.empty:
        print("No SoC metrics found - plotting only latency and jitter")
        soc_available = False
    else:
        soc_available = True

    # Create figure with 4 subplots (added threshold exceedances)
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))

    groups = latency_stats['group_index']

    # ===== PLOT 1: LATENCY =====
    ax1.plot(groups, latency_stats['avg_latency_us'], 'b-', linewidth=2,
             label=f'Average latency (top-{top_n})')
    ax1.fill_between(groups, latency_stats['min_latency_us'],
                     latency_stats['max_latency_us'],
                     alpha=0.2, color='blue', label=f'Min-max range')

    # Add threshold line
    ax1.axhline(y=threshold_us, color='red', linestyle='--',
                linewidth=2, label=f'Threshold: {threshold_us} µs', alpha=0.7)

    overall_avg_latency = latency_stats['avg_latency_us'].mean()
    ax1.axhline(y=overall_avg_latency, color='black', linestyle=':',
                linewidth=1.5, label=f'Overall avg: {overall_avg_latency:.1f} µs')

    ax1.set_ylabel('Latency (µs)')
    ax1.set_xlabel('Group Number')

    # Build title with session info
    title = f'Latency Analysis (top-{top_n} worst per group)'
    if session_info:
        stress_status = "WITH STRESS" if session_info['target_stress'] == 'on' else "NO STRESS"
        title += f'\nBoard: {session_info["target_board"]} | Kernel: {session_info["target_kernel"]}'
        title += f'\nInterval: {session_info["interval_us"]} µs | Measurements/group: {session_info["measurements_per_group"]}'

    ax1.set_title(title, fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper right')

    # ===== PLOT 2: JITTER =====
    ax2.plot(groups, latency_stats['jitter_us'], 'g-', linewidth=2,
             label='RMS Jitter')

    overall_avg_jitter = latency_stats['jitter_us'].mean()
    ax2.axhline(y=overall_avg_jitter, color='black', linestyle=':',
                linewidth=1.5, label=f'Overall avg: {overall_avg_jitter:.1f} µs')

    ax2.set_ylabel('Jitter (µs)')
    ax2.set_xlabel('Group Number')
    ax2.set_title('Jitter Analysis (RMS - Standard Deviation)')
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper right')

    # ===== PLOT 3: THRESHOLD EXCEEDANCES =====
    # Bar chart of exceedances per group
    colors = ['red' if x > 0 else 'green' for x in latency_stats['exceeds_threshold_count']]
    bars = ax3.bar(groups, latency_stats['exceeds_threshold_count'],
                   color=colors, alpha=0.7, edgecolor='black', linewidth=0.5)

    # Add percentage labels on top of bars
    for i, (count, percent) in enumerate(zip(latency_stats['exceeds_threshold_count'],
                                              latency_stats['exceeds_threshold_percent'])):
        if count > 0:
            ax3.text(groups.iloc[i], count + 0.5, f'{percent:.0f}%',
                    ha='center', va='bottom', fontsize=8, rotation=45)

    ax3.set_ylabel(f'Count exceeding {threshold_us} µs')
    ax3.set_xlabel('Group Number')
    ax3.set_title(f'Threshold Exceedances (limit: {threshold_us} µs)')
    ax3.grid(True, alpha=0.3, axis='y')

    # Add total exceedances info
    total_exceeds = latency_stats['exceeds_threshold_count'].sum()
    groups_with_exceeds = (latency_stats['exceeds_threshold_count'] > 0).sum()
    ax3.text(0.98, 0.98, f'Total: {total_exceeds} | Groups with exceeds: {groups_with_exceeds}',
            transform=ax3.transAxes, ha='right', va='top',
            fontsize=9, bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7))

    # ===== PLOT 4: SoC METRICS =====
    if soc_available:
        # Merge data to ensure alignment
        merged = pd.merge(latency_stats, soc_metrics, on='group_index', how='left')

        # Plot CPU usage
        ax4.plot(merged['group_index'], merged['cpu_percent'], 'r-', linewidth=2,
                label='CPU Usage % (avg per group)', marker='o', markersize=3)

        # Plot memory usage on same axis
        ax4.plot(merged['group_index'], merged['memory_percent'], 'orange',
                linewidth=2, label='Memory Usage % (avg per group)', marker='s', markersize=3)

        # Add max lines if available
        if 'cpu_max' in merged.columns and merged['cpu_max'].notna().any():
            ax4.plot(merged['group_index'], merged['cpu_max'], 'r--',
                    linewidth=1, alpha=0.5, label='CPU Max %')
        if 'mem_max' in merged.columns and merged['mem_max'].notna().any():
            ax4.plot(merged['group_index'], merged['mem_max'], 'orange',
                    linewidth=1, alpha=0.5, linestyle='--', label='Memory Max %')

        ax4.set_ylabel('Usage %')
        ax4.set_xlabel('Group Number')
        ax4.set_title('SoC System Load (Target Device)')
        ax4.grid(True, alpha=0.3)
        ax4.legend(loc='upper right', fontsize=8)

        # Add statistics box
        stats_text = (
            f"CPU: avg={merged['cpu_percent'].mean():.1f}%, "
            f"max={merged['cpu_max'].max() if 'cpu_max' in merged.columns and merged['cpu_max'].notna().any() else merged['cpu_percent'].max():.1f}%\n"
            f"MEM: avg={merged['memory_percent'].mean():.1f}%, "
            f"max={merged['mem_max'].max() if 'mem_max' in merged.columns and merged['mem_max'].notna().any() else merged['memory_percent'].max():.1f}%"
        )
        ax4.text(0.02, 0.02, stats_text, transform=ax4.transAxes,
                fontsize=9, verticalalignment='bottom',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7))
    else:
        ax4.text(0.5, 0.5, 'No SoC metrics available',
                transform=ax4.transAxes, ha='center', va='center',
                fontsize=14, style='italic', color='gray')
        ax4.set_ylabel('Usage %')
        ax4.set_xlabel('Group Number')
        ax4.set_title('SoC System Load (Target Device) - No Data')
        ax4.grid(True, alpha=0.3)

    # Set integer ticks for x-axis on all subplots
    for ax in [ax1, ax2, ax3, ax4]:
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))

    # Add session statistics footer
    if session_info:
        footer_text = (
            f"Session duration: {session_info['groups_count']} groups | "
            f"Falls: {session_info['falls_count']} | "
            f"Worst count per group: {session_info['worst_count']} | "
            f"Threshold: {threshold_us} µs | "
            f"Total exceeds: {session_info.get('total_exceeds', 0)}"
        )
        fig.text(0.5, 0.01, footer_text, ha='center', fontsize=9,
                bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.7))

    plt.tight_layout()
    plt.subplots_adjust(bottom=0.08 if session_info else 0.05)

    # Determine output filename
    if output is None and session_id:
        output = generate_plot_filename(db_path, session_id, "comprehensive", threshold_us)
        print(f"Auto-generated filename: {output}")

    if output:
        plt.savefig(output, dpi=150, bbox_inches='tight')
        print(f"Comprehensive plot saved: {output}")
    else:
        plt.show()


def generate_plot_filename(db_path: str, session_id: int,
                          plot_type: str = "comprehensive",
                          threshold_us: int = DEFAULT_THRESHOLD_US) -> str:
    """
    Generate filename for plot based on session info.
    Format: sessionid_board_kernel_interval_worstcount_avg_latency_stress.png
    """
    info = get_session_info(db_path, session_id, threshold_us)

    if not info:
        # Fallback if session info not found
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"session_{session_id}_{timestamp}.png"

    # Get board name (sanitized)
    board = info['target_board'] if info['target_board'] else "unknown"
    board_clean = sanitize_filename(board)

    # Get kernel version (sanitized)
    kernel = info['target_kernel'] if info['target_kernel'] else "unknown"
    kernel_clean = sanitize_filename(kernel)

    # Get stress status
    stress = info['target_stress'] if info['target_stress'] else "off"
    stress_suffix = "stress_on" if stress == 'on' else "stress_off"

    # Get measurement parameters
    interval_us = info['interval_us'] if info['interval_us'] else 300
    worst_count = info['worst_count'] if info['worst_count'] else 125


    filename = f"{session_id}_{board_clean}_{kernel_clean}_{interval_us}_{worst_count}_{stress_suffix}.png"

    return filename


def plot_latency_with_soc(db_path: str, session_id: int = None,
                          output: str = None, top_n: int = 125,
                          threshold_us: int = DEFAULT_THRESHOLD_US) -> None:
    """Plot latency with SoC metrics overlay (alternative layout)."""
    latency_stats = get_latency_stats(db_path, session_id, top_n, threshold_us)
    soc_metrics = get_soc_metrics(db_path, session_id)

    if latency_stats is None or latency_stats.empty:
        print("No latency data to display")
        return

    session_info = get_session_info(db_path, session_id, threshold_us) if session_id else None

    # Create figure with 2 subplots (latency+soc on top, threshold below)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

    groups = latency_stats['group_index']

    # ===== PLOT 1: LATENCY + SoC =====
    color = 'tab:blue'
    ax1.set_xlabel('Group Number')
    ax1.set_ylabel('Latency (µs)', color=color)
    line1 = ax1.plot(groups, latency_stats['avg_latency_us'], color=color,
                     linewidth=2, label='Average Latency')[0]
    ax1.fill_between(groups, latency_stats['min_latency_us'],
                     latency_stats['max_latency_us'],
                     alpha=0.2, color=color)
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.grid(True, alpha=0.3)

    # Add threshold line
    ax1.axhline(y=threshold_us, color='red', linestyle='--',
                linewidth=2, label=f'Threshold: {threshold_us} µs', alpha=0.7)

    # Add overall average line
    overall_avg = latency_stats['avg_latency_us'].mean()
    ax1.axhline(y=overall_avg, color='darkblue', linestyle=':',
                linewidth=1.5, label=f'Avg Latency: {overall_avg:.1f} µs')

    # Create second y-axis for SoC metrics
    if soc_metrics is not None and not soc_metrics.empty:
        ax1_twin = ax1.twinx()
        color2 = 'tab:red'

        merged = pd.merge(latency_stats, soc_metrics, on='group_index', how='left')

        # Plot CPU
        line2 = ax1_twin.plot(merged['group_index'], merged['cpu_percent'],
                              color=color2, linewidth=2,
                              label='CPU Usage %', marker='o', markersize=3)[0]

        # Plot Memory
        line3 = ax1_twin.plot(merged['group_index'], merged['memory_percent'],
                              color='orange', linewidth=2,
                              label='Memory Usage %', marker='s', markersize=3)[0]

        ax1_twin.set_ylabel('SoC Usage %', color=color2)
        ax1_twin.tick_params(axis='y', labelcolor=color2)

        # Combine legends
        lines = [line1, line2, line3]
        labels = [l.get_label() for l in lines]
        ax1.legend(lines, labels, loc='upper left')
    else:
        ax1.legend(loc='upper left')

    # Build title
    title = f'Latency vs SoC Load'
    if session_info:
        stress_status = "WITH STRESS" if session_info['target_stress'] == 'on' else "NO STRESS"
        title += f'\nBoard: {session_info["target_board"]} | Kernel: {session_info["target_kernel"]}'
        title += f' | Interval: {session_info["interval_us"]} µs'

    ax1.set_title(title)

    # ===== PLOT 2: THRESHOLD EXCEEDANCES =====
    colors = ['red' if x > 0 else 'green' for x in latency_stats['exceeds_threshold_count']]
    bars = ax2.bar(groups, latency_stats['exceeds_threshold_count'],
                   color=colors, alpha=0.7, edgecolor='black', linewidth=0.5)

    # Add percentage labels
    for i, (count, percent) in enumerate(zip(latency_stats['exceeds_threshold_count'],
                                              latency_stats['exceeds_threshold_percent'])):
        if count > 0:
            ax2.text(groups.iloc[i], count + 0.5, f'{percent:.0f}%',
                    ha='center', va='bottom', fontsize=8, rotation=45)

    ax2.set_ylabel(f'Count exceeding {threshold_us} µs')
    ax2.set_xlabel('Group Number')
    ax2.set_title(f'Threshold Exceedances (limit: {threshold_us} µs)')
    ax2.grid(True, alpha=0.3, axis='y')

    # Add total exceedances info
    total_exceeds = latency_stats['exceeds_threshold_count'].sum()
    groups_with_exceeds = (latency_stats['exceeds_threshold_count'] > 0).sum()
    ax2.text(0.98, 0.98, f'Total: {total_exceeds} | Groups with exceeds: {groups_with_exceeds}',
            transform=ax2.transAxes, ha='right', va='top',
            fontsize=9, bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7))

    ax2.xaxis.set_major_locator(MaxNLocator(integer=True))

    plt.tight_layout()

    # Determine output filename
    if output is None and session_id:
        output = generate_plot_filename(db_path, session_id, "latency_soc", threshold_us)
        print(f"Auto-generated filename: {output}")

    if output:
        plt.savefig(output, dpi=150, bbox_inches='tight')
        print(f"Plot saved: {output}")
    else:
        plt.show()



def plot_latency_only(db_path: str, session_id: int = None,
                       output: str = None, top_n: int = 125,
                       threshold_us: int = DEFAULT_THRESHOLD_US) -> None:
    """Plot latency for a single session (avg + max, no SoC overlay)."""
    latency_stats = get_latency_stats(db_path, session_id, top_n, threshold_us)

    if latency_stats is None or latency_stats.empty:
        print("No latency data to display")
        return

    session_info = get_session_info(db_path, session_id, threshold_us) if session_id else None

    fig, ax = plt.subplots(1, 1, figsize=(14, 6))

    groups = latency_stats['group_index']

    color = 'tab:blue'
    ax.set_xlabel('Group Number')
    ax.set_ylabel('Latency (µs)', color=color)
    ax.plot(groups, latency_stats['avg_latency_us'], color=color,
            linewidth=1.5, label='Average Latency')
    ax.fill_between(groups, latency_stats['avg_latency_us'],
                    latency_stats['max_latency_us'],
                    alpha=0.2, color=color, label='Max Latency Range')
    ax.axhline(y=threshold_us, color='red', linestyle='--',
               linewidth=1.5, label=f'Threshold: {threshold_us} µs', alpha=0.7)

    overall_avg = latency_stats['avg_latency_us'].mean()
    ax.axhline(y=overall_avg, color='darkblue', linestyle=':',
               linewidth=1.5, label=f'Overall Avg: {overall_avg:.1f} µs')
    ax.tick_params(axis='y', labelcolor=color)
    ax.grid(True, alpha=0.3)

    title = 'Latency Analysis'
    if session_info:
        title = f"{session_info['target_board']} / {session_info['target_kernel']} — Latency"

    ax.set_title(title)
    ax.legend(loc='upper left')
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))

    plt.tight_layout()

    if not output and session_id:
        output = generate_plot_filename(db_path, session_id, "latency", threshold_us)
    if output:
        plt.savefig(output, dpi=150, bbox_inches='tight')
        print(f"Plot saved to {output}")
    else:
        plt.show()


def plot_jitter_only(db_path: str, session_id: int = None,
                     output: str = None, top_n: int = 125,
                     threshold_us: int = DEFAULT_THRESHOLD_US) -> None:
    """Plot jitter for a single session (no SoC overlay)."""
    latency_stats = get_latency_stats(db_path, session_id, top_n, threshold_us)

    if latency_stats is None or latency_stats.empty:
        print("No jitter data to display")
        return

    session_info = get_session_info(db_path, session_id, threshold_us) if session_id else None

    fig, ax = plt.subplots(1, 1, figsize=(14, 6))

    groups = latency_stats['group_index']
    color = 'tab:green'

    ax.set_xlabel('Group Number')
    ax.set_ylabel('Jitter (µs)', color=color)
    ax.plot(groups, latency_stats['jitter_us'], color=color,
            linewidth=1.5, label='RMS Jitter')
    ax.tick_params(axis='y', labelcolor=color)
    ax.grid(True, alpha=0.3)

    overall_jit = latency_stats['jitter_us'].mean()
    ax.axhline(y=overall_jit, color='darkgreen', linestyle=':',
               linewidth=1.5, label=f'Overall Avg Jitter: {overall_jit:.1f} µs')

    title = 'Jitter Analysis'
    if session_info:
        title = f"{session_info['target_board']} / {session_info['target_kernel']} — Jitter"

    ax.set_title(title)
    ax.legend(loc='upper left')
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))

    plt.tight_layout()

    if not output and session_id:
        output = generate_plot_filename(db_path, session_id, "jitter", threshold_us)
    if output:
        plt.savefig(output, dpi=150, bbox_inches='tight')
        print(f"Plot saved to {output}")
    else:
        plt.show()


def plot_jitter_with_soc(db_path: str, session_id: int = None,
                         output: str = None,
                         threshold_us: int = DEFAULT_THRESHOLD_US) -> None:
    """Plot jitter with SoC metrics overlay."""

    info = get_session_info(db_path, session_id, threshold_us)
    if info is None:
        print("Session not found")
        return

    latency_stats = get_latency_stats(db_path, session_id, info['worst_count'], threshold_us)
    soc_metrics = get_soc_metrics(db_path, session_id)

    if latency_stats is None or latency_stats.empty:
        print("No jitter data to display")
        return

    session_info = get_session_info(db_path, session_id, threshold_us) if session_id else None

    # Create figure with 2 subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

    groups = latency_stats['group_index']

    # ===== PLOT 1: JITTER + SoC =====
    color = 'tab:green'
    ax1.set_xlabel('Group Number')
    ax1.set_ylabel('Jitter (µs)', color=color)
    line1 = ax1.plot(groups, latency_stats['jitter_us'], color=color,
                     linewidth=2, label='RMS Jitter')[0]
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.grid(True, alpha=0.3)

    # Add overall average line
    overall_avg = latency_stats['jitter_us'].mean()
    ax1.axhline(y=overall_avg, color='darkgreen', linestyle=':',
                linewidth=1.5, label=f'Avg Jitter: {overall_avg:.1f} µs')

    # Second y-axis for SoC metrics
    if soc_metrics is not None and not soc_metrics.empty:
        ax1_twin = ax1.twinx()
        color2 = 'tab:red'

        merged = pd.merge(latency_stats, soc_metrics, on='group_index', how='left')

        line2 = ax1_twin.plot(merged['group_index'], merged['cpu_percent'],
                              color=color2, linewidth=2,
                              label='CPU Usage %', marker='o', markersize=3)[0]

        line3 = ax1_twin.plot(merged['group_index'], merged['memory_percent'],
                              color='orange', linewidth=2,
                              label='Memory Usage %', marker='s', markersize=3)[0]

        ax1_twin.set_ylabel('SoC Usage %', color=color2)
        ax1_twin.tick_params(axis='y', labelcolor=color2)

        lines = [line1, line2, line3]
        labels = [l.get_label() for l in lines]
        ax1.legend(lines, labels, loc='upper left')
    else:
        ax1.legend(loc='upper left')

    # Build title
    title = f'Jitter vs SoC Load'
    if session_info:
        stress_status = "WITH STRESS" if session_info['target_stress'] == 'on' else "NO STRESS"
        title += f'\nBoard: {session_info["target_board"]} | Kernel: {session_info["target_kernel"]}'

    ax1.set_title(title)

    # ===== PLOT 2: THRESHOLD EXCEEDANCES =====
    colors = ['red' if x > 0 else 'green' for x in latency_stats['exceeds_threshold_count']]
    bars = ax2.bar(groups, latency_stats['exceeds_threshold_count'],
                   color=colors, alpha=0.7, edgecolor='black', linewidth=0.5)

    # Add percentage labels
    for i, (count, percent) in enumerate(zip(latency_stats['exceeds_threshold_count'],
                                              latency_stats['exceeds_threshold_percent'])):
        if count > 0:
            ax2.text(groups.iloc[i], count + 0.5, f'{percent:.0f}%',
                    ha='center', va='bottom', fontsize=8, rotation=45)

    ax2.set_ylabel(f'Count exceeding {threshold_us} µs')
    ax2.set_xlabel('Group Number')
    ax2.set_title(f'Threshold Exceedances (limit: {threshold_us} µs)')
    ax2.grid(True, alpha=0.3, axis='y')

    total_exceeds = latency_stats['exceeds_threshold_count'].sum()
    groups_with_exceeds = (latency_stats['exceeds_threshold_count'] > 0).sum()
    ax2.text(0.98, 0.98, f'Total: {total_exceeds} | Groups with exceeds: {groups_with_exceeds}',
            transform=ax2.transAxes, ha='right', va='top',
            fontsize=9, bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7))

    ax2.xaxis.set_major_locator(MaxNLocator(integer=True))

    plt.tight_layout()

    # Determine output filename
    if output is None and session_id:
        output = generate_plot_filename(db_path, session_id, "jitter_soc", threshold_us)
        print(f"Auto-generated filename: {output}")

    if output:
        plt.savefig(output, dpi=150, bbox_inches='tight')
        print(f"Plot saved: {output}")
    else:
        plt.show()


def list_sessions(db_path: str, threshold_us: int = DEFAULT_THRESHOLD_US) -> None:
    """
    Display list of all sessions with detailed statistics including target info and stress.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            g.session_id,
            MIN(g.created_at) as first_seen,
            MAX(g.created_at) as last_seen,
            COUNT(DISTINCT g.id) as groups_count,
            AVG(g.jitter_us) as avg_jitter,
            AVG(l.latency_us) as avg_latency,
            MAX(g.target_board) as target_board,
            MAX(g.target_kernel) as target_kernel,
            MAX(g.target_stress) as target_stress,
            MIN(g.delay_us) as interval_us,
            MIN(g.worst_count) as worst_count,
            (SELECT AVG(cpu_percent) FROM soc_metrics s
             WHERE s.session_id = g.session_id) as avg_cpu,
            (SELECT AVG(memory_percent) FROM soc_metrics s
             WHERE s.session_id = g.session_id) as avg_mem,
            (SELECT COUNT(*) FROM events e
             WHERE e.session_id = g.session_id AND e.event_type = 'fall') as falls,
            (SELECT COUNT(*) FROM latencies l2 JOIN groups g2 ON l2.group_id = g2.id
             WHERE g2.session_id = g.session_id AND l2.latency_us > ?) as exceeds
        FROM groups g
        LEFT JOIN latencies l ON g.id = l.group_id
        GROUP BY g.session_id
        ORDER BY first_seen DESC
    ''', (threshold_us,))

    sessions = cursor.fetchall()
    conn.close()

    if not sessions:
        print("No sessions in database")
        return

    print("\n" + "="*180)
    print(f"{'Session':<12} {'Board':<12} {'Kernel':<20} {'Stress':<8} {'Groups':<8} {'Interval':<10} {'Worst':<6} {'Avg Lat':<10} {'Avg Jit':<10} {'Exceeds':<10} {'Avg CPU':<10} {'Avg MEM':<10} {'Falls':<8} {'First Seen'}")
    print("="*180)

    for sess in sessions:
        (sess_id, first, last, groups, jitter, latency,
         board, kernel, stress, interval, worst_count, cpu, mem, falls, exceeds) = sess

        # Format values
        board_str = board if board else "unknown"
        kernel_str = (kernel[:18] + "..") if kernel and len(kernel) > 20 else (kernel if kernel else "unknown")
        stress_str = stress if stress else "off"
        interval_str = f"{interval}µs" if interval else "N/A"
        worst_str = str(worst_count) if worst_count else "N/A"
        exceeds_str = str(exceeds) if exceeds is not None else "0"
        cpu_str = f"{cpu:.1f}%" if cpu else "N/A"
        mem_str = f"{mem:.1f}%" if mem else "N/A"

        # Highlight stress sessions and sessions with exceeds
        stress_marker = "⚡" if stress_str == "on" else "○"
        exceed_marker = "⚠️" if exceeds and exceeds > 0 else "✓"

        print(f"{sess_id:<12} {board_str:<12} {kernel_str:<20} {stress_str:<8} {groups:<8} {interval_str:<10} {worst_str:<6} "
              f"{latency:<10.2f} {jitter:<10.2f} {exceeds_str:<10} {cpu_str:<10} {mem_str:<10} {falls:<8} {first[:19]} {stress_marker}{exceed_marker}")

    print("="*180)

    # Summary statistics
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(DISTINCT target_board) FROM groups WHERE target_board IS NOT NULL AND target_board != "unknown"')
    board_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(DISTINCT target_kernel) FROM groups WHERE target_kernel IS NOT NULL AND target_kernel != "unknown"')
    kernel_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM groups WHERE target_stress = "on"')
    stress_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM groups WHERE target_stress = "off"')
    no_stress_count = cursor.fetchone()[0]

    cursor.execute(f'SELECT COUNT(*) FROM latencies l JOIN groups g ON l.group_id = g.id WHERE l.latency_us > {threshold_us}')
    total_exceeds = cursor.fetchone()[0]

    print(f"\nSummary:")
    print(f"  Total sessions: {len(sessions)}")
    print(f"  Different boards: {board_count}")
    print(f"  Different kernels: {kernel_count}")
    print(f"  Sessions with stress: {stress_count}")
    print(f"  Sessions without stress: {no_stress_count}")
    print(f"  Total latency exceedances (>{threshold_us} µs): {total_exceeds}")



def show_session_details(db_path: str, session_id: int, threshold_us: int = DEFAULT_THRESHOLD_US) -> None:
    """
    Show detailed information about a specific session.
    """
    info = get_session_info(db_path, session_id, threshold_us)

    if not info:
        print(f"Session {session_id} not found")
        return

    stress_status = "on" if info['target_stress'] == 'on' else "off"
    payload_status = "on" if info.get('target_payload') == 'on' else "off"

    print("\n" + "="*80)
    print(f"SESSION DETAILS: {session_id}")
    print("="*80)
    print(f"Target Board:  {info['target_board']}")
    print(f"Target Kernel: {info['target_kernel']}")
    print(f"Stress:  {stress_status}")
    print(f"Payload: {payload_status}")
    print(f"Start Time:    {info['start_time']}")
    print(f"End Time:      {info['end_time']}")
    print(f"Duration:      {info['groups_count']} groups")
    print(f"\nMeasurement Parameters:")
    print(f"  Interval:            {info['interval_us']} µs")
    print(f"  Measurements/group:  {info['measurements_per_group']}")
    print(f"  Worst count/group:   {info['worst_count']}")
    print(f"\nPerformance Metrics:")
    avg_latency = info.get('avg_latency')
    if avg_latency is not None:
        print(f"  Average Latency:     {avg_latency:.2f} µs")
    else:
        print(f"  Average Latency:     N/A")
    print(f"  Average Jitter:      {info['avg_jitter']:.2f} µs")
    print(f"  Falls:               {info['falls_count']}")

    print(f"\nThreshold Exceedances (>{threshold_us} µs):")
    print(f"  Total exceeds:       {info.get('total_exceeds', 0)}")
    print(f"  Groups with exceeds: {info.get('groups_with_exceeds', 0)}")
    if info.get('max_exceed'):
        print(f"  Maximum exceed:      {info['max_exceed']} µs")

    if info.get('avg_cpu'):
        print(f"\nSoC Metrics:")
        print(f"  Average CPU:         {info['avg_cpu']:.1f}%")
        print(f"  Average Memory:      {info['avg_mem']:.1f}%")
        print(f"  Max CPU:             {info['max_cpu']:.1f}%")
        print(f"  Max Memory:          {info['max_mem']:.1f}%")

    print("="*80)


def plot_session_compare(db_path: str, session_id_1: int, session_id_2: int,
                         output: str = None, top_n: int = 125,
                         threshold_us: int = DEFAULT_THRESHOLD_US,
                         mode: str = "combined",
                         normalize: bool = False) -> None:
    """Compare latency and jitter between two sessions."""
    df1 = get_latency_stats(db_path, session_id_1, top_n, threshold_us)
    df2 = get_latency_stats(db_path, session_id_2, top_n, threshold_us)

    if df1 is None or df1.empty:
        print(f"No data for session {session_id_1}")
        return
    if df2 is None or df2.empty:
        print(f"No data for session {session_id_2}")
        return

    info1 = get_session_info(db_path, session_id_1, threshold_us)
    info2 = get_session_info(db_path, session_id_2, threshold_us)

    def board_label(info, sid):
        board = info.get('target_board', '?') if info else '?'
        kernel = info.get('target_kernel', '?') if info else '?'
        return f"[{sid}] {board} / {kernel}"

    label1 = board_label(info1, session_id_1)
    label2 = board_label(info2, session_id_2)

    show_latency = mode in ("combined", "latency", "overlay")
    show_jitter  = mode in ("combined", "jitter", "overlay")

    # Save original ranges for legend before normalization
    max1_range = (df1['max_latency_us'].min(), df1['max_latency_us'].max())
    max2_range = (df2['max_latency_us'].min(), df2['max_latency_us'].max())
    jit1_range = (df1['jitter_us'].min(), df1['jitter_us'].max())
    jit2_range = (df2['jitter_us'].min(), df2['jitter_us'].max())

    # In combined mode, normalize both graphs to [0,1] for visual comparability
    do_normalize = normalize
    if do_normalize:
        def scale(s):
            mn, mx = s.min(), s.max()
            return (s - mn) / (mx - mn) if mx > mn else s
        df1 = df1.copy()
        df2 = df2.copy()
        df1['max_latency_us'] = scale(df1['max_latency_us'])
        df2['max_latency_us'] = scale(df2['max_latency_us'])
        df1['jitter_us'] = scale(df1['jitter_us'])
        df2['jitter_us'] = scale(df2['jitter_us'])
        ylabel = 'Normalized'
    else:
        ylabel = 'µs'

    if mode == "combined":
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    else:
        fig, ax1 = plt.subplots(1, 1, figsize=(14, 6))

    if show_latency:
        if mode == "overlay":
            # Session 1: avg = lighter, max = darker blue
            ax1.plot(df1['group_index'], df1['max_latency_us'], color='darkblue', linewidth=1, alpha=0.5,
                    label=f'{label1} max  ({max1_range[0]:.0f}–{max1_range[1]:.0f} µs)')
            ax1.plot(df1['group_index'], df1['avg_latency_us'], color='#7eb8da', linewidth=1.5, alpha=0.9,
                    label=f'{label1} avg')
            # Session 2: avg = lighter, max = darker red
            ax1.plot(df2['group_index'], df2['max_latency_us'], color='darkred', linewidth=1, alpha=0.5,
                    label=f'{label2} max  ({max2_range[0]:.0f}–{max2_range[1]:.0f} µs)')
            ax1.plot(df2['group_index'], df2['avg_latency_us'], color='#e88482', linewidth=1.5, alpha=0.9,
                    label=f'{label2} avg')
        else:
            # Session 1: avg = lighter, max = darker blue
            ax1.plot(df1['group_index'], df1['max_latency_us'], color='darkblue', linewidth=1, alpha=0.5,
                    label=f'{label1} max  ({max1_range[0]:.0f}–{max1_range[1]:.0f} µs)')
            ax1.plot(df1['group_index'], df1['avg_latency_us'], color='#7eb8da', linewidth=1.5, alpha=0.9,
                    label=f'{label1} avg')
            ax1.fill_between(df1['group_index'], df1['min_latency_us'],
                             df1['max_latency_us'], alpha=0.1, color='blue')

            # Session 2: avg = lighter, max = darker red
            ax1.plot(df2['group_index'], df2['max_latency_us'], color='darkred', linewidth=1, alpha=0.5,
                    label=f'{label2} max  ({max2_range[0]:.0f}–{max2_range[1]:.0f} µs)')
            ax1.plot(df2['group_index'], df2['avg_latency_us'], color='#e88482', linewidth=1.5, alpha=0.9,
                    label=f'{label2} avg')
            ax1.fill_between(df2['group_index'], df2['min_latency_us'],
                             df2['max_latency_us'], alpha=0.1, color='red')

            ax1.axhline(y=threshold_us, color='red', linestyle='--',
                        linewidth=1, alpha=0.7, label=f'Threshold: {threshold_us} µs')

            ax1.set_title('Latency Comparison')
            ax1.set_ylabel(f'Latency ({ylabel})')
            ax1.legend(fontsize=8, loc='upper right')

    if show_jitter:
        if mode == "overlay":
            ax1.plot(df1['group_index'], df1['jitter_us'], 'b--', linewidth=1, alpha=0.7,
                     label=f'{label1} rms  ({jit1_range[0]:.0f}–{jit1_range[1]:.0f} µs)')
            ax1.plot(df2['group_index'], df2['jitter_us'], 'r--', linewidth=1, alpha=0.7,
                     label=f'{label2} rms  ({jit2_range[0]:.0f}–{jit2_range[1]:.0f} µs)')
            ax1.set_title('Max Latency & Jitter Comparison')
            ax1.set_ylabel(f'µs')
            lines, labels = ax1.get_legend_handles_labels()
            ax1.legend(lines, labels, fontsize=8, loc='upper right')
        elif mode == "combined":
            ax2.plot(df1['group_index'], df1['jitter_us'], 'b-', linewidth=1, alpha=0.8)
            ax2.plot(df2['group_index'], df2['jitter_us'], 'r-', linewidth=1, alpha=0.8)
            ax2.set_title('Jitter Comparison')
            ax2.set_ylabel(f'Jitter ({ylabel})')
            ax2.legend([f'{label1}  ({jit1_range[0]:.0f}–{jit1_range[1]:.0f} µs)',
                        f'{label2}  ({jit2_range[0]:.0f}–{jit2_range[1]:.0f} µs)'],
                       fontsize=8, loc='upper right')
        else:
            ax1.plot(df1['group_index'], df1['jitter_us'], 'b-', linewidth=1, alpha=0.8)
            ax1.plot(df2['group_index'], df2['jitter_us'], 'r-', linewidth=1, alpha=0.8)
            ax1.set_title('Jitter Comparison')
            ax1.set_ylabel(f'Jitter ({ylabel})')
            ax1.legend([f'{label1}  ({jit1_range[0]:.0f}–{jit1_range[1]:.0f} µs)',
                        f'{label2}  ({jit2_range[0]:.0f}–{jit2_range[1]:.0f} µs)'],
                        fontsize=8, loc='upper right')

    # Use same Y-axis range for combined/overlay modes (real µs, uniform scale)
    if mode in ("combined", "overlay") and not normalize:
        max_y = 0
        for df in [df1, df2]:
            for col in ['max_latency_us', 'avg_latency_us', 'jitter_us']:
                if col in df.columns:
                    max_y = max(max_y, df[col].max())
        ax1.set_ylim(0, max_y * 1.05)
        if mode == "combined":
            ax2.set_ylim(0, max_y * 1.05)

    plt.tight_layout()
    if not output:
        suffix = "_normalized" if normalize else ""
        output = f"compare_{session_id_1}_{session_id_2}_{mode}{suffix}.png"
    if output:
        plt.savefig(output, dpi=150, bbox_inches='tight')
        print(f"Plot saved to {output}")
    else:
        plt.show()


def plot_trace_breakdown(db_path: str, session_id: int,
                          output: str = None) -> None:
    """Plot trace stage breakdown: stacked bars per group, grouped by host."""
    trace = get_trace_metrics(db_path, session_id)
    if trace is None or trace.empty:
        print("No trace metrics to display")
        return

    hosts = trace['host'].unique()
    stages = trace['stage'].unique()
    groups = sorted(trace['group_index'].unique())

    fig, axes = plt.subplots(len(hosts), 1, figsize=(14, 4 * len(hosts)),
                             squeeze=False)
    colors = plt.cm.Set2(np.linspace(0, 1, len(stages)))

    for hidx, host in enumerate(hosts):
        ax = axes[hidx][0]
        host_data = trace[trace['host'] == host]
        bottom = np.zeros(len(groups))
        for sidx, stage in enumerate(stages):
            stage_data = host_data[host_data['stage'] == stage]
            vals = []
            for g in groups:
                row = stage_data[stage_data['group_index'] == g]
                vals.append(row['avg_us'].values[0] if not row.empty else 0)
            ax.bar(groups, vals, bottom=bottom, label=stage,
                   color=colors[sidx % len(colors)], width=0.8)
            bottom += np.array(vals)

        ax.set_xlabel('Group Number')
        ax.set_ylabel('Average Time (µs)')
        ax.set_title(f'Trace Stage Breakdown — {host}')
        ax.legend(fontsize=8, loc='upper right')
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    if output:
        plt.savefig(output, dpi=150, bbox_inches='tight')
        print(f"Trace plot saved: {output}")
    else:
        plt.show()


def plot_event_timeline(db_path: str, session_id: int,
                        output: str = None) -> None:
    """Plot event timeline with annotations."""
    events = get_events(db_path, session_id)
    if events is None or events.empty:
        print("No events to display")
        return

    info = get_session_info(db_path, session_id)
    groups_count = info['groups_count'] if info else 100

    fig, ax = plt.subplots(1, 1, figsize=(14, 3))

    fall_events = events[events['event_type'] == 'fall']
    rec_events = events[events['event_type'] == 'recovery']
    other = events[~events['event_type'].isin(['fall', 'recovery', 'start', 'stop'])]

    # Draw timeline
    ax.set_xlim(0, groups_count)
    ax.set_ylim(0, 1)
    ax.axhline(y=0.5, color='gray', linewidth=1, alpha=0.5)

    # Start
    start_row = events[events['event_type'] == 'start']
    if not start_row.empty:
        ax.annotate('START', xy=(0, 0.5), fontsize=9, fontweight='bold',
                    ha='left', va='bottom', color='green')

    # Stop
    stop_row = events[events['event_type'] == 'stop']
    if not stop_row.empty:
        grp = stop_row.iloc[0].get('group_index')
        if grp is None or pd.isna(grp):
            grp = groups_count
        ax.annotate('STOP', xy=(grp, 0.5), fontsize=9, fontweight='bold',
                    ha='right', va='bottom', color='blue')

    # Falls
    for _, row in fall_events.iterrows():
        grp = row['group_index']
        if pd.notna(grp):
            ax.plot(grp, 0.5, 'rv', markersize=12, zorder=5)
            ax.annotate(f'FALL', xy=(grp, 0.55), fontsize=8, color='red',
                        ha='center', rotation=45)

    # Recoveries
    for _, row in rec_events.iterrows():
        grp = row['group_index']
        if pd.notna(grp):
            ax.plot(grp, 0.5, 'g^', markersize=12, zorder=5)
            ax.annotate(f'RECOVER', xy=(grp, 0.45), fontsize=8, color='green',
                        ha='center', rotation=45)

    # Other events
    for _, row in other.iterrows():
        grp = row['group_index']
        if pd.notna(grp):
            ax.plot(grp, 0.5, 'yo', markersize=8, alpha=0.6)

    # Falls count summary
    n_falls = len(fall_events)
    ax.set_title(f'Session Event Timeline — {n_falls} fall(s), {len(rec_events)} recovery(ies)')
    ax.set_xlabel('Group Number')
    ax.set_yticks([])
    ax.grid(True, alpha=0.3, axis='x')

    plt.tight_layout()
    if output:
        plt.savefig(output, dpi=150, bbox_inches='tight')
        print(f"Event timeline saved: {output}")
    else:
        plt.show()


def generate_markdown_summary(db_path: str, session_id: int,
                               output: str = None,
                               threshold_us: int = DEFAULT_THRESHOLD_US) -> str:
    """Generate a markdown summary string for the session."""
    info = get_session_info(db_path, session_id, threshold_us)
    if not info:
        return f"# Session {session_id}\n\nSession not found.\n"

    val = validate_session(db_path, session_id)
    stress = "ON" if info.get('target_stress') == 'on' else "OFF"

    lines = []
    lines.append(f"# Session {session_id} — Report")
    lines.append("")
    lines.append(f"**Board:** {info['target_board']}  ")
    lines.append(f"**Kernel:** {info['target_kernel']}  ")
    lines.append(f"**Stress:** {stress}  ")
    lines.append(f"**Payload:** {'ON' if info.get('target_payload') == 'on' else 'OFF'}  ")
    lines.append(f"**Interval:** {info['interval_us']} µs  ")
    lines.append(f"**Measurements/group:** {info['measurements_per_group']}  ")
    lines.append(f"**Worst count/group:** {info['worst_count']}  ")
    lines.append("")
    lines.append("## Performance")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---:|")
    lines.append(f"| Groups | {info['groups_count']} |")

    avg_jit = info.get('avg_jitter')
    jitter_str = f"{avg_jit:.1f}" if avg_jit is not None else "N/A"
    lines.append(f"| Average Jitter | {jitter_str} µs |")
    lines.append(f"| Falls | {info['falls_count']} |")

    # Latency stats from actual data
    stats = get_latency_stats(db_path, session_id, info['worst_count'], threshold_us)
    if stats is not None and not stats.empty:
        lines.append(f"| Min Latency (per-group avg) | {stats['avg_latency_us'].min():.1f} µs |")
        lines.append(f"| Max Latency (per-group avg) | {stats['avg_latency_us'].max():.1f} µs |")
        lines.append(f"| Overall Latency (global avg) | {stats['avg_latency_us'].mean():.1f} µs |")
        lines.append(f"| Global Max Latency | {stats['max_latency_us'].max():.1f} µs |")

    lines.append("")
    lines.append("## Threshold Exceedances")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---:|")
    lines.append(f"| Threshold | {threshold_us} µs |")
    lines.append(f"| Total exceeds | {info.get('total_exceeds', 0)} |")
    lines.append(f"| Groups with exceeds | {info.get('groups_with_exceeds', 0)} |")
    if info.get('max_exceed'):
        lines.append(f"| Maximum exceed | {info['max_exceed']} µs |")

    if info.get('avg_cpu'):
        lines.append("")
        lines.append("## SoC Metrics")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|---|---:|")
        lines.append(f"| Average CPU | {info['avg_cpu']:.1f}% |")
        lines.append(f"| Max CPU | {info['max_cpu']:.1f}% |")
        lines.append(f"| Average Memory | {info['avg_mem']:.1f}% |")
        lines.append(f"| Max Memory | {info['max_mem']:.1f}% |")

    lines.append("")
    lines.append("## Data Integrity")
    lines.append("")
    for p in val.get('passed', []):
        lines.append(f"- ✅ {p}")
    for w in val.get('warnings', []):
        lines.append(f"- ⚠️ {w}")
    for f in val.get('failed', []):
        lines.append(f"- ❌ {f}")

    if val.get('trace_hosts'):
        lines.append("")
        lines.append("## Trace Sources")
        lines.append("")
        for host, cnt in val['trace_hosts'].items():
            lines.append(f"- **{host}**: {cnt} measurements")

    md = "\n".join(lines)
    if output:
        with open(output, 'w', encoding='utf-8') as f:
            f.write(md)
        print(f"Markdown summary saved: {output}")
    return md


def generate_html_index(session_id: int, output_dir: str,
                         md_content: str = "",
                         png_files: list = None) -> str:
    """Generate an HTML index page linking all report assets."""
    if png_files is None:
        png_files = []

    lines = []
    lines.append("<!DOCTYPE html>")
    lines.append("<html lang='en'>")
    lines.append("<head>")
    lines.append(f"<title>Session {session_id} — Report</title>")
    lines.append("<style>")
    lines.append("body { font-family: sans-serif; max-width: 960px; margin: 2em auto; "
                 "padding: 0 1em; background: #fafafa; color: #333; }")
    lines.append("h1 { border-bottom: 2px solid #ddd; padding-bottom: 0.3em; }")
    lines.append("img { max-width: 100%; border: 1px solid #ccc; "
                 "border-radius: 4px; margin: 1em 0; }")
    lines.append(".summary { background: #fff; border: 1px solid #ddd; "
                 "border-radius: 4px; padding: 1em; margin: 1em 0; }")
    lines.append(".pass { color: #090; } .warn { color: #960; } .fail { color: #c00; }")
    lines.append("table { border-collapse: collapse; margin: 1em 0; }")
    lines.append("th, td { border: 1px solid #ddd; padding: 0.4em 0.8em; "
                 "text-align: right; }")
    lines.append("th { background: #eee; }")
    lines.append("</style>")
    lines.append("</head>")
    lines.append("<body>")

    # Render markdown summary as simple HTML
    in_table = False
    for line in md_content.split('\n'):
        if line.startswith('# '):
            lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith('## '):
            lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith('| ') and '---' in line:
            continue
        elif line.startswith('| '):
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if not in_table:
                lines.append("<table>")
                lines.append("<tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>")
                in_table = True
            else:
                lines.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        else:
            if in_table:
                lines.append("</table>")
                in_table = False
            if line.startswith('- ✅'):
                lines.append(f"<p class='pass'>{line}</p>")
            elif line.startswith('- ⚠️'):
                lines.append(f"<p class='warn'>{line}</p>")
            elif line.startswith('- ❌'):
                lines.append(f"<p class='fail'>{line}</p>")
            elif line.strip():
                # Inline formatting
                formatted = line
                if line.strip().startswith('**') and line.strip().endswith('  '):
                    formatted = line.strip().rstrip(' ')
                lines.append(f"<p>{formatted}</p>")
    if in_table:
        lines.append("</table>")

    # Image gallery
    if png_files:
        lines.append("<h2>Graphs</h2>")
        for png in png_files:
            rel = os.path.basename(png)
            lines.append(f"<img src='{rel}' alt='{rel}' title='{rel}'>")

    lines.append("</body>")
    lines.append("</html>")

    html = "\n".join(lines)
    index_path = os.path.join(output_dir, "index.html")
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"HTML index saved: {index_path}")
    return index_path


def report(db_path: str, session_id: int, output_dir: str = "report",
           top_n: int = 125, threshold_us: int = DEFAULT_THRESHOLD_US) -> str:
    """Generate a complete session report: plots, summary, and HTML index."""
    os.makedirs(output_dir, exist_ok=True)
    print(f"\n{'=' * 60}")
    print(f"  Session Report: {session_id}")
    print(f"  Output: {output_dir}/")
    print(f"{'=' * 60}\n")

    base = os.path.join(output_dir, f"session_{session_id}")

    # 1. Comprehensive plot
    all_png = f"{base}_all.png"
    plot_comprehensive_analysis(db_path, session_id, all_png, top_n, threshold_us)

    # 2. Latency + SoC
    lat_soc_png = f"{base}_latency_soc.png"
    plot_latency_with_soc(db_path, session_id, lat_soc_png, top_n, threshold_us)

    # 3. Jitter + SoC
    jit_soc_png = f"{base}_jitter_soc.png"
    plot_jitter_with_soc(db_path, session_id, jit_soc_png, threshold_us)

    # 4. Trace breakdown
    trace_png = f"{base}_trace.png"
    plot_trace_breakdown(db_path, session_id, trace_png)

    # 5. Event timeline
    event_png = f"{base}_events.png"
    plot_event_timeline(db_path, session_id, event_png)

    # 6. Markdown summary
    md_path = f"{base}_summary.md"
    md_content = generate_markdown_summary(db_path, session_id, md_path, threshold_us)

    # 7. HTML index
    pngs = [all_png, lat_soc_png, jit_soc_png, trace_png, event_png]
    html_path = generate_html_index(session_id, output_dir, md_content, pngs)

    print(f"\n{'=' * 60}")
    print(f"  Report complete: {html_path}")
    print(f"{'=' * 60}\n")
    return html_path


def main():
    """Main entry point with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description='Arduino Data Visualization with SoC Metrics',
        epilog='For more information, see README.md'
    )
    parser.add_argument('db', help='Path to SQLite database')
    parser.add_argument('--session', type=int, help='Session ID (if not specified, all sessions)')
    parser.add_argument('--output', '-o', help='Save plot to file instead of displaying')
    parser.add_argument('--top', type=int, default=125,
                       help='Number of worst latencies to analyze')
    parser.add_argument('--limit', type=int, default=DEFAULT_THRESHOLD_US,
                       help=f'Latency threshold in microseconds (default: {DEFAULT_THRESHOLD_US})')

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Comprehensive analysis (4 plots)
    parser_comp = subparsers.add_parser('all', help='Show all plots (latency, jitter, exceeds, SoC)')

    # Latency + SoC
    parser_lat_soc = subparsers.add_parser('latency+soc', help='Latency with SoC overlay and exceeds')

    parser_lat = subparsers.add_parser('latency', help='Latency plot only (no SoC overlay)')

    parser_jit = subparsers.add_parser('jitter', help='Jitter plot only (no SoC overlay)')

    parser_jit_soc = subparsers.add_parser('jitter+soc', help='Jitter with SoC overlay and exceeds')

    # Legacy commands
    subparsers.add_parser('sessions', help='List all sessions with target info')
    parser_details = subparsers.add_parser('details', help='Show detailed session information')
    parser_details.add_argument('session_id', type=int, help='Session ID to show details')

    # Session comparison
    parser_comp = subparsers.add_parser('compare', help='Compare latency/jitter between two sessions')
    parser_comp.add_argument('session_id_1', type=int, help='First session ID')
    parser_comp.add_argument('session_id_2', type=int, help='Second session ID')
    parser_comp.add_argument('--mode', choices=['combined', 'latency', 'jitter', 'overlay'], default='combined',
                            help='What to compare: combined (default), latency only, jitter only, or overlay (both on one graph)')
    parser_comp.add_argument('--normalize', action='store_true',
                            help='Normalize Y-axis to [0,1] for visual comparison of different scales')

    # Report
    parser_report = subparsers.add_parser('report', help='Generate complete session report (plots, summary, HTML)')
    parser_report.add_argument('--session', type=int, default=None,
                              help='Session ID (default: latest session)')
    parser_report.add_argument('--output-dir', '-o', default='report',
                              help='Output directory for report files (default: report/)')
    parser_report.add_argument('--top', type=int, default=125,
                              help='Number of worst latencies to analyze')
    parser_report.add_argument('--limit', type=int, default=DEFAULT_THRESHOLD_US,
                              help=f'Latency threshold in microseconds (default: {DEFAULT_THRESHOLD_US})')
    parser_report.add_argument('--stress', choices=['on', 'off'], default=None,
                              help='Filter latest session by stress status')

    # Validate
    parser_val = subparsers.add_parser('validate', help='Validate session data integrity')
    parser_val.add_argument('--session', type=int, default=None,
                           help='Session ID (default: latest session)')

    # Trace breakdown
    parser_trace = subparsers.add_parser('trace', help='Plot trace stage breakdown')
    parser_trace.add_argument('--session', type=int, default=None,
                             help='Session ID (default: latest session)')
    parser_trace.add_argument('--output', '-o', default=None,
                             help='Save plot to file')

    # Event timeline
    parser_ev = subparsers.add_parser('events', help='Plot event timeline')
    parser_ev.add_argument('--session', type=int, default=None,
                          help='Session ID (default: latest session)')
    parser_ev.add_argument('--output', '-o', default=None,
                          help='Save plot to file')

    # Latest
    parser_latest = subparsers.add_parser('latest', help='Show latest session ID')
    parser_latest.add_argument('--stress', choices=['on', 'off'], default=None,
                              help='Filter by stress status')

    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"Error: Database file {args.db} not found")
        return

    try:
        if args.command == 'sessions':
            list_sessions(args.db, args.limit)

        elif args.command == 'details':
            show_session_details(args.db, args.session_id, args.limit)

        elif args.command == 'all':
            plot_comprehensive_analysis(args.db, args.session, args.output, args.top, args.limit)

        elif args.command == 'latency+soc':
            plot_latency_with_soc(args.db, args.session, args.output, args.top, args.limit)

        elif args.command == 'latency':
            plot_latency_only(args.db, args.session, args.output, args.top, args.limit)

        elif args.command == 'jitter':
            plot_jitter_only(args.db, args.session, args.output, args.top, args.limit)

        elif args.command == 'jitter+soc':
            plot_jitter_with_soc(args.db, args.session, args.output, args.limit)

        elif args.command == 'compare':
            plot_session_compare(args.db, args.session_id_1, args.session_id_2,
                                args.output, args.top, args.limit, args.mode,
                                args.normalize)

        elif args.command == 'latest':
            sid = latest_session(args.db, args.stress)
            if sid:
                info = get_session_info(args.db, sid, args.limit)
                stress_str = "with stress" if info and info['target_stress'] == 'on' else "no stress"
                print(f"Latest session: {sid} ({stress_str})")
            else:
                print("No sessions found")

        elif args.command == 'validate':
            sid = args.session or latest_session(args.db)
            if not sid:
                print("No session specified and no sessions in database")
                return
            val = validate_session(args.db, sid)
            info = get_session_info(args.db, sid, args.limit)
            label = f"Session {sid}"
            if info:
                label += f" ({info['target_board']}, stress={'on' if info['target_stress']=='on' else 'off'})"
            print(f"\nValidation: {label}")
            print("=" * 60)
            if val['passed']:
                print("\nPassed:")
                for p in val['passed']:
                    print(f"  ✅ {p}")
            if val['warnings']:
                print("\nWarnings:")
                for w in val['warnings']:
                    print(f"  ⚠️  {w}")
            if val['failed']:
                print("\nFailed:")
                for f in val['failed']:
                    print(f"  ❌ {f}")
            print()

        elif args.command == 'trace':
            sid = args.session or latest_session(args.db)
            if not sid:
                print("No session specified and no sessions in database")
                return
            plot_trace_breakdown(args.db, sid, args.output)

        elif args.command == 'events':
            sid = args.session or latest_session(args.db)
            if not sid:
                print("No session specified and no sessions in database")
                return
            plot_event_timeline(args.db, sid, args.output)

        elif args.command == 'report':
            sid = args.session or latest_session(args.db, args.stress)
            if not sid:
                print("No session specified and no sessions in database")
                return
            report(args.db, sid, args.output_dir, args.top, args.limit)

        else:
            print("Please specify a command. Available commands:")
            print("  all          - comprehensive view (4 plots: latency, jitter, exceeds, SoC)")
            print("  latency+soc  - latency with SoC overlay and exceeds")
            print("  latency      - latency plot only (no SoC)")
            print("  jitter+soc   - jitter with SoC overlay and exceeds")
            print("  jitter       - jitter plot only (no SoC)")
            print("  sessions     - list all sessions with target info and exceed counts")
            print("  details      - show detailed session information")
            print("  compare      - compare latency/jitter between two sessions")
            print("  report       - generate complete session report (plots + summary + HTML)")
            print("  validate     - check session data integrity")
            print("  trace        - plot trace stage breakdown")
            print("  events       - plot event timeline")
            print("  latest       - show latest session ID")
            print("\nOptional parameters:")
            print(f"  --limit      - latency threshold in µs (default: {DEFAULT_THRESHOLD_US})")
            print("  --top        - number of worst latencies to analyze")
            print("  --output     - save plot to file (auto-named if not specified)")
            print("  --session    - session ID (auto-detects latest if omitted)")
            print("\nFor more information, see README.md")

    except ValueError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
