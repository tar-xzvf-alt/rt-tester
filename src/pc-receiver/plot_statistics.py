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

def setup_session_logging(session_id: int, log_dir: str = "logs") -> logging.Logger:
    """
    Set up a separate log file for a specific session.
    """
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

def get_latency_stats(db_path: str, session_id: int = None, top_n: int = 25) -> pd.DataFrame:
    """
    Calculate statistics for the worst N latencies in each group.
    """
    if top_n < 1 or top_n > 25:
        raise ValueError("top_n must be between 1 and 25")
    
    conn = sqlite3.connect(db_path)
    
    query = '''
        SELECT 
            g.session_id,
            g.group_index,
            g.jitter_us,
            l.latency_us,
            l.rank_in_group
        FROM groups g
        JOIN latencies l ON g.id = l.group_id
        WHERE l.rank_in_group <= ?
    '''
    params = [top_n]
    
    if session_id is not None:
        query += ' AND g.session_id = ?'
        params.append(session_id)
    
    query += ' ORDER BY g.group_index, l.rank_in_group'
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    if df.empty:
        return None
    
    stats = df.groupby('group_index').agg({
        'latency_us': ['mean', 'min', 'max', 'count'],
        'jitter_us': 'first'
    }).reset_index()
    
    stats.columns = ['group_index', 'avg_latency_us', 'min_latency_us', 
                     'max_latency_us', 'latencies_used', 'jitter_us']
    
    return stats

def get_soc_metrics(db_path: str, session_id: int = None) -> pd.DataFrame:
    """
    Get SoC (target device) metrics from database.
    
    Args:
        db_path: Path to SQLite database
        session_id: Optional session ID to filter data
    
    Returns:
        DataFrame with SoC metrics per group
    """
    conn = sqlite3.connect(db_path)
    
    query = '''
        SELECT 
            session_id,
            group_index,
            cpu_percent,
            memory_percent,
            load_1min
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

def plot_comprehensive_analysis(db_path: str, session_id: int = None, 
                               output: str = None, top_n: int = 25) -> None:
    """
    Generate comprehensive plot with latency, jitter, and SoC metrics.
    
    Args:
        db_path: Path to SQLite database
        session_id: Optional session ID to filter data
        output: Output file path for saving the plot
        top_n: Number of worst latencies to consider
    """
    # Get all data
    latency_stats = get_latency_stats(db_path, session_id, top_n)
    soc_metrics = get_soc_metrics(db_path, session_id)
    
    if latency_stats is None or latency_stats.empty:
        print("No latency data to display")
        return
    
    if soc_metrics is None or soc_metrics.empty:
        print("⚠️ No SoC metrics found - plotting only latency and jitter")
        soc_available = False
    else:
        soc_available = True
    
    # Create figure with 3 subplots
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 12), sharex=True)
    
    groups = latency_stats['group_index']
    
    # ===== PLOT 1: LATENCY =====
    ax1.plot(groups, latency_stats['avg_latency_us'], 'b-', linewidth=2, 
             label=f'Average latency (top-{top_n})')
    ax1.fill_between(groups, latency_stats['min_latency_us'], 
                     latency_stats['max_latency_us'], 
                     alpha=0.2, color='blue', label=f'Min-max range')
    
    overall_avg_latency = latency_stats['avg_latency_us'].mean()
    ax1.axhline(y=overall_avg_latency, color='black', linestyle='--', 
                linewidth=1.5, label=f'Overall avg: {overall_avg_latency:.1f} µs')
    
    ax1.set_ylabel('Latency (µs)')
    ax1.set_title(f'Latency Analysis (top-{top_n} worst per group)' + 
                  (f' (session {session_id})' if session_id else ''))
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper right')
    
    # ===== PLOT 2: JITTER =====
    ax2.plot(groups, latency_stats['jitter_us'], 'g-', linewidth=2, 
             label='Jitter')
    
    overall_avg_jitter = latency_stats['jitter_us'].mean()
    ax2.axhline(y=overall_avg_jitter, color='black', linestyle='--', 
                linewidth=1.5, label=f'Overall avg: {overall_avg_jitter:.1f} µs')
    
    ax2.set_ylabel('Jitter (µs)')
    ax2.set_title('Jitter Analysis')
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper right')
    
    # ===== PLOT 3: SoC METRICS =====
    if soc_available:
        # Merge data to ensure alignment
        merged = pd.merge(latency_stats, soc_metrics, on='group_index', how='left')
        
        # Plot CPU usage
        ax3.plot(merged['group_index'], merged['cpu_percent'], 'r-', linewidth=2, 
                label='CPU Usage %', marker='o', markersize=3)
        
        # Plot memory usage on same axis
        ax3.plot(merged['group_index'], merged['memory_percent'], 'orange', 
                linewidth=2, label='Memory Usage %', marker='s', markersize=3)
        
        # Add load average as text annotations for peaks
        load_peaks = merged.nlargest(5, 'load_1min')[['group_index', 'load_1min']]
        for _, row in load_peaks.iterrows():
            ax3.annotate(f'load={row["load_1min"]:.2f}', 
                        (row['group_index'], 95),
                        fontsize=8, rotation=45, ha='center')
        
        # Add zero line for reference
        ax3.axhline(y=0, color='gray', linestyle='-', linewidth=0.5, alpha=0.5)
        
        ax3.set_ylabel('Usage %')
        ax3.set_title('SoC System Load (Target Device)')
        ax3.grid(True, alpha=0.3)
        ax3.legend(loc='upper right')
        
        # Add statistics box
        stats_text = (
            f"CPU: avg={merged['cpu_percent'].mean():.1f}%, "
            f"max={merged['cpu_percent'].max():.1f}%\n"
            f"MEM: avg={merged['memory_percent'].mean():.1f}%, "
            f"max={merged['memory_percent'].max():.1f}%\n"
            f"Load: avg={merged['load_1min'].mean():.2f}"
        )
        ax3.text(0.02, 0.02, stats_text, transform=ax3.transAxes,
                fontsize=9, verticalalignment='bottom',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7))
    else:
        ax3.text(0.5, 0.5, 'No SoC metrics available', 
                transform=ax3.transAxes, ha='center', va='center',
                fontsize=14, style='italic', color='gray')
        ax3.set_ylabel('Usage %')
        ax3.set_title('SoC System Load (Target Device) - No Data')
        ax3.grid(True, alpha=0.3)
    
    # Common X axis
    ax3.set_xlabel('Group Number')
    ax3.xaxis.set_major_locator(MaxNLocator(integer=True))
    
    # Add session information
    if session_id:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM system_events 
            WHERE session_id = ? AND event_type = 'fall'
        ''', (session_id,))
        falls_count = cursor.fetchone()[0]
        conn.close()
        
        if falls_count > 0:
            fig.text(0.98, 0.98, f'⚠️ Falls in session: {falls_count}',
                    transform=fig.transFigure, ha='right', va='top',
                    fontsize=12, fontweight='bold',
                    bbox=dict(boxstyle='round', facecolor='lightcoral', alpha=0.7))
    
    plt.tight_layout()
    
    if output:
        plt.savefig(output, dpi=150, bbox_inches='tight')
        print(f"✓ Comprehensive plot saved: {output}")
    else:
        plt.show()

def plot_latency_with_soc(db_path: str, session_id: int = None, 
                          output: str = None, top_n: int = 25) -> None:
    """
    Plot latency with SoC metrics overlay (alternative layout).
    """
    # Get all data
    latency_stats = get_latency_stats(db_path, session_id, top_n)
    soc_metrics = get_soc_metrics(db_path, session_id)
    
    if latency_stats is None or latency_stats.empty:
        print("No latency data to display")
        return
    
    fig, ax1 = plt.subplots(figsize=(14, 8))
    
    groups = latency_stats['group_index']
    
    # Plot latency
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
    
    # Add overall average line
    overall_avg = latency_stats['avg_latency_us'].mean()
    ax1.axhline(y=overall_avg, color='darkblue', linestyle='--', 
                linewidth=1.5, label=f'Avg Latency: {overall_avg:.1f} µs')
    
    # Create second y-axis for SoC metrics
    if soc_metrics is not None and not soc_metrics.empty:
        ax2 = ax1.twinx()
        color = 'tab:red'
        
        # Merge to ensure alignment
        merged = pd.merge(latency_stats, soc_metrics, on='group_index', how='left')
        
        # Plot CPU
        line2 = ax2.plot(merged['group_index'], merged['cpu_percent'], 
                         color=color, linewidth=2, 
                         label='CPU Usage %', marker='o', markersize=3)[0]
        
        # Plot Memory on same axis with different style
        line3 = ax2.plot(merged['group_index'], merged['memory_percent'], 
                         color='orange', linewidth=2, 
                         label='Memory Usage %', marker='s', markersize=3)[0]
        
        ax2.set_ylabel('SoC Usage %', color=color)
        ax2.tick_params(axis='y', labelcolor=color)
        
        # Add load peaks as annotations
        load_peaks = merged.nlargest(3, 'load_1min')[['group_index', 'load_1min']]
        for _, row in load_peaks.iterrows():
            ax2.annotate(f'load={row["load_1min"]:.2f}', 
                        (row['group_index'], 90),
                        fontsize=8, ha='center')
        
        # Combine legends
        lines = [line1, line2, line3]
        labels = [l.get_label() for l in lines]
        ax1.legend(lines, labels, loc='upper left')
    else:
        ax1.legend(loc='upper left')
        ax1.text(0.98, 0.1, 'No SoC metrics available', 
                transform=ax1.transAxes, ha='right', va='bottom',
                fontsize=10, style='italic', color='gray',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7))
    
    ax1.set_title(f'Latency vs SoC Load' + 
                  (f' (session {session_id})' if session_id else ''))
    ax1.xaxis.set_major_locator(MaxNLocator(integer=True))
    
    plt.tight_layout()
    
    if output:
        plt.savefig(output, dpi=150, bbox_inches='tight')
        print(f"✓ Plot saved: {output}")
    else:
        plt.show()

def plot_jitter_with_soc(db_path: str, session_id: int = None, 
                         output: str = None) -> None:
    """
    Plot jitter with SoC metrics overlay.
    """
    # Get data
    conn = sqlite3.connect(db_path)
    
    query = '''
        SELECT group_index, jitter_us
        FROM groups
    '''
    params = []
    
    if session_id is not None:
        query += ' WHERE session_id = ?'
        params.append(session_id)
    
    query += ' ORDER BY group_index'
    
    jitter_df = pd.read_sql_query(query, conn, params=params)
    soc_df = get_soc_metrics(db_path, session_id)
    conn.close()
    
    if jitter_df.empty:
        print("No jitter data to display")
        return
    
    fig, ax1 = plt.subplots(figsize=(14, 8))
    
    groups = jitter_df['group_index']
    
    # Plot jitter
    color = 'tab:green'
    ax1.set_xlabel('Group Number')
    ax1.set_ylabel('Jitter (µs)', color=color)
    line1 = ax1.plot(groups, jitter_df['jitter_us'], color=color, 
                     linewidth=2, label='Jitter')[0]
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.grid(True, alpha=0.3)
    
    # Add overall average line
    overall_avg = jitter_df['jitter_us'].mean()
    ax1.axhline(y=overall_avg, color='darkgreen', linestyle='--', 
                linewidth=1.5, label=f'Avg Jitter: {overall_avg:.1f} µs')
    
    # Second y-axis for SoC metrics
    if soc_df is not None and not soc_df.empty:
        ax2 = ax1.twinx()
        color = 'tab:red'
        
        merged = pd.merge(jitter_df, soc_df, on='group_index', how='left')
        
        # Plot CPU
        line2 = ax2.plot(merged['group_index'], merged['cpu_percent'], 
                         color=color, linewidth=2, 
                         label='CPU Usage %', marker='o', markersize=3)[0]
        
        # Plot Memory
        line3 = ax2.plot(merged['group_index'], merged['memory_percent'], 
                         color='orange', linewidth=2, 
                         label='Memory Usage %', marker='s', markersize=3)[0]
        
        ax2.set_ylabel('SoC Usage %', color=color)
        ax2.tick_params(axis='y', labelcolor=color)
        
        # Combine legends
        lines = [line1, line2, line3]
        labels = [l.get_label() for l in lines]
        ax1.legend(lines, labels, loc='upper left')
    else:
        ax1.legend(loc='upper left')
    
    ax1.set_title(f'Jitter vs SoC Load' + 
                  (f' (session {session_id})' if session_id else ''))
    ax1.xaxis.set_major_locator(MaxNLocator(integer=True))
    
    plt.tight_layout()
    
    if output:
        plt.savefig(output, dpi=150, bbox_inches='tight')
        print(f"✓ Plot saved: {output}")
    else:
        plt.show()

def list_sessions(db_path: str) -> None:
    """
    Display list of all sessions with basic statistics including SoC data.
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
            (SELECT AVG(cpu_percent) FROM soc_metrics s 
             WHERE s.session_id = g.session_id) as avg_cpu,
            (SELECT AVG(memory_percent) FROM soc_metrics s 
             WHERE s.session_id = g.session_id) as avg_mem,
            (SELECT COUNT(*) FROM system_events e 
             WHERE e.session_id = g.session_id AND e.event_type = 'fall') as falls
        FROM groups g
        LEFT JOIN latencies l ON g.id = l.group_id
        GROUP BY g.session_id
        ORDER BY first_seen DESC
    ''')
    
    sessions = cursor.fetchall()
    conn.close()
    
    if not sessions:
        print("No sessions in database")
        return
    
    print("\n📋 SESSIONS IN DATABASE")
    print("="*130)
    print(f"{'Session':<12} {'Groups':<8} {'Avg Lat':<10} {'Avg Jit':<10} {'Avg CPU':<10} {'Avg MEM':<10} {'Falls':<8} {'Status':<10} {'First Seen'}")
    print("-"*130)
    
    for sess in sessions:
        sess_id, first, last, groups, jitter, latency, cpu, mem, falls = sess
        
        # Session status
        if falls == 0:
            status = "✅ OK"
        elif falls > 0:
            status = "⚠️ Falls"
        else:
            status = "✅"
        
        cpu_str = f"{cpu:.1f}%" if cpu else "N/A"
        mem_str = f"{mem:.1f}%" if mem else "N/A"
        
        print(f"{sess_id:<12} {groups:<8} {latency:<10.2f} {jitter:<10.2f} "
              f"{cpu_str:<10} {mem_str:<10} {falls:<8} {status:<10} {first[:19]}")
    
    print("="*130)

def main():
    """Main entry point with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description='Arduino Data Visualization with SoC Metrics',
        epilog='For more information, see README.md'
    )
    parser.add_argument('db', help='Path to SQLite database')
    parser.add_argument('--session', type=int, help='Session ID (if not specified, all sessions)')
    parser.add_argument('--output', '-o', help='Save plot to file instead of displaying')
    parser.add_argument('--top', type=int, default=25, 
                       help='Number of worst latencies to analyze (1-25, default: 25)')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Comprehensive analysis (3 plots)
    parser_comp = subparsers.add_parser('all', help='Show all plots (latency, jitter, SoC)')
    
    # Latency + SoC
    parser_lat_soc = subparsers.add_parser('latency+soc', help='Latency with SoC overlay')
    
    # Jitter + SoC
    parser_jit_soc = subparsers.add_parser('jitter+soc', help='Jitter with SoC overlay')
    
    # Legacy commands
    subparsers.add_parser('sessions', help='List all sessions with SoC stats')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.db):
        print(f"Error: Database file {args.db} not found")
        return
    
    try:
        if args.command == 'sessions':
            list_sessions(args.db)
        
        elif args.command == 'all':
            plot_comprehensive_analysis(args.db, args.session, args.output, args.top)
        
        elif args.command == 'latency+soc':
            plot_latency_with_soc(args.db, args.session, args.output, args.top)
        
        elif args.command == 'jitter+soc':
            plot_jitter_with_soc(args.db, args.session, args.output)
        
        else:
            print("Please specify a command. Available commands:")
            print("  all          - comprehensive view (3 plots: latency, jitter, SoC)")
            print("  latency+soc  - latency with SoC overlay (dual axis)")
            print("  jitter+soc   - jitter with SoC overlay (dual axis)")
            print("  sessions     - list all sessions with SoC stats")
            print("\nFor more information, see README.md")
            
    except ValueError as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()