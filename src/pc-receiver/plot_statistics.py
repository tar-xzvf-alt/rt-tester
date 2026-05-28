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
        'target_stress': 'first'
    }).reset_index()
    
    stats.columns = ['group_index', 'avg_latency_us', 'min_latency_us', 
                     'max_latency_us', 'latencies_used', 'jitter_us',
                     'target_board', 'target_kernel', 'target_stress']
    
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
            'groups_count': row[6],
            'avg_jitter': row[7],
            'interval_us': row[8],
            'measurements_per_group': row[9],
            'worst_count': row[10]
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
        title += f'\nSession {session_id} | Board: {session_info["target_board"]} | Kernel: {session_info["target_kernel"]} | {stress_status}'
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
        title += f'\nSession {session_id} | Board: {session_info["target_board"]} | Kernel: {session_info["target_kernel"]} | {stress_status}'
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
        title += f'\nSession {session_id} | Board: {session_info["target_board"]} | Kernel: {session_info["target_kernel"]} | {stress_status}'
    
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
    
    stress_status = "WITH STRESS" if info['target_stress'] == 'on' else "NO STRESS"
    
    print("\n" + "="*80)
    print(f"SESSION DETAILS: {session_id}")
    print("="*80)
    print(f"Target Board:  {info['target_board']}")
    print(f"Target Kernel: {info['target_kernel']}")
    print(f"Stress State:  {stress_status}")
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
                         threshold_us: int = DEFAULT_THRESHOLD_US) -> None:
    """Compare max latency and jitter between two sessions with normalized Y-axis."""
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
        stress = info.get('target_stress', 'off') if info else 'off'
        return f"[{sid}] {board} / {kernel} / stress={stress}"

    label1 = board_label(info1, session_id_1)
    label2 = board_label(info2, session_id_2)

    def normalize(s):
        mn, mx = s.min(), s.max()
        if mx > mn:
            return (s - mn) / (mx - mn)
        return s

    norm_max1 = normalize(df1['max_latency_us'])
    norm_max2 = normalize(df2['max_latency_us'])
    norm_jit1 = normalize(df1['jitter_us'])
    norm_jit2 = normalize(df2['jitter_us'])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # Left: max latency comparison (normalized left Y, real µs right Y)
    real_max_min = min(df1['max_latency_us'].min(), df2['max_latency_us'].min())
    real_max_max = max(df1['max_latency_us'].max(), df2['max_latency_us'].max())

    ax1.plot(df1['group_index'], norm_max1, 'b-', linewidth=1, alpha=0.8)
    ax1.plot(df2['group_index'], norm_max2, 'r-', linewidth=1, alpha=0.8)
    ax1.set_title('Max Latency Comparison (normalized)')
    ax1.set_ylabel('Normalized')
    ax1_r = ax1.twinx()
    ax1_r.set_ylim(real_max_min, real_max_max)
    ax1_r.set_ylabel('Max latency (µs)')
    ax1_r.plot([], [])  # dummy to align legend
    ax1.legend([f'{label1}  ({df1["max_latency_us"].min():.0f}–{df1["max_latency_us"].max():.0f} µs)',
                f'{label2}  ({df2["max_latency_us"].min():.0f}–{df2["max_latency_us"].max():.0f} µs)'],
               fontsize=8, loc='upper right')

    # Right: jitter comparison (normalized left Y, real µs right Y)
    real_jit_min = min(df1['jitter_us'].min(), df2['jitter_us'].min())
    real_jit_max = max(df1['jitter_us'].max(), df2['jitter_us'].max())

    ax2.plot(df1['group_index'], norm_jit1, 'b-', linewidth=1, alpha=0.8)
    ax2.plot(df2['group_index'], norm_jit2, 'r-', linewidth=1, alpha=0.8)
    ax2.set_title('Jitter Comparison (normalized)')
    ax2.set_ylabel('Normalized')
    ax2_r = ax2.twinx()
    ax2_r.set_ylim(real_jit_min, real_jit_max)
    ax2_r.set_ylabel('Jitter (µs)')
    ax2_r.plot([], [])  # dummy to align legend
    ax2.legend([f'{label1}  ({df1["jitter_us"].min():.0f}–{df1["jitter_us"].max():.0f} µs)',
                f'{label2}  ({df2["jitter_us"].min():.0f}–{df2["jitter_us"].max():.0f} µs)'],
               fontsize=8, loc='upper right')

    plt.tight_layout()
    if output:
        plt.savefig(output, dpi=150, bbox_inches='tight')
        print(f"Plot saved to {output}")
    else:
        plt.show()


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
    
    # Jitter + SoC
    parser_jit_soc = subparsers.add_parser('jitter+soc', help='Jitter with SoC overlay and exceeds')
    
    # Legacy commands
    subparsers.add_parser('sessions', help='List all sessions with target info')
    parser_details = subparsers.add_parser('details', help='Show detailed session information')
    parser_details.add_argument('session_id', type=int, help='Session ID to show details')
    
    # Session comparison
    parser_comp = subparsers.add_parser('compare', help='Compare latency/jitter between two sessions')
    parser_comp.add_argument('session_id_1', type=int, help='First session ID')
    parser_comp.add_argument('session_id_2', type=int, help='Second session ID')
    
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
        
        elif args.command == 'jitter+soc':
            plot_jitter_with_soc(args.db, args.session, args.output, args.limit)
        
        elif args.command == 'compare':
            plot_session_compare(args.db, args.session_id_1, args.session_id_2,
                                args.output, args.top, args.limit)
        
        else:
            print("Please specify a command. Available commands:")
            print("  all          - comprehensive view (4 plots: latency, jitter, exceeds, SoC)")
            print("  latency+soc  - latency with SoC overlay and exceeds")
            print("  jitter+soc   - jitter with SoC overlay and exceeds")
            print("  sessions     - list all sessions with target info and exceed counts")
            print("  details      - show detailed session information")
            print("  compare      - compare latency/jitter between two sessions (normalized Y-axis)")
            print("\nOptional parameters:")
            print(f"  --limit      - latency threshold in µs (default: {DEFAULT_THRESHOLD_US})")
            print("  --top        - number of worst latencies to analyze")
            print("  --output     - save plot to file (auto-named if not specified)")
            print("\nFor more information, see README.md")
            
    except ValueError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()