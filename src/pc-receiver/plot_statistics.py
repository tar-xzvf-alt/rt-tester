#!/usr/bin/env python3
"""
Arduino Data Visualization Tool

This script provides visualization and analysis tools for data collected from Arduino
measurement system. It supports latency analysis, jitter plots, and session monitoring.
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
    
    Args:
        session_id: Session identifier
        log_dir: Directory for log files
    
    Returns:
        Logger instance configured for the session
    """
    # Create logs directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    
    # Create logger for this session
    logger = logging.getLogger(f"session_{session_id}")
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create file handler
    log_file = os.path.join(log_dir, f"session_{session_id}.log")
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(file_handler)
    
    return logger

def get_latency_stats(db_path: str, session_id: int = None, top_n: int = 25) -> pd.DataFrame:
    """
    Calculate statistics for the worst N latencies in each group.
    
    Args:
        db_path: Path to SQLite database
        session_id: Optional session ID to filter data
        top_n: Number of worst latencies to consider (1-25)
    
    Returns:
        DataFrame with latency statistics per group
    
    Raises:
        ValueError: If top_n is outside valid range
    """
    if top_n < 1 or top_n > 25:
        raise ValueError("top_n must be between 1 and 25")
    
    conn = sqlite3.connect(db_path)
    
    # Query groups and their latencies
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
    
    # Group by group_index and calculate statistics
    stats = df.groupby('group_index').agg({
        'latency_us': ['mean', 'min', 'max', 'count'],
        'jitter_us': 'first'  # Jitter is the same for entire group
    }).reset_index()
    
    # Rename columns for convenience
    stats.columns = ['group_index', 'avg_latency_us', 'min_latency_us', 
                     'max_latency_us', 'latencies_used', 'jitter_us']
    
    return stats

def plot_latency_over_time(db_path: str, session_id: int = None, 
                          output: str = None, top_n: int = 25) -> None:
    """
    Generate latency plot over groups considering top_n worst latencies.
    
    Args:
        db_path: Path to SQLite database
        session_id: Optional session ID to filter data
        output: Output file path for saving the plot
        top_n: Number of worst latencies to consider
    """
    stats = get_latency_stats(db_path, session_id, top_n)
    
    if stats is None or stats.empty:
        print("No data to display")
        return
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    groups = stats['group_index']
    
    # Mean values line
    ax.plot(groups, stats['avg_latency_us'], 'b-', linewidth=2, 
            label=f'Average latency (top-{top_n})')
    
    # Min-max range
    ax.fill_between(groups, stats['min_latency_us'], stats['max_latency_us'], 
                    alpha=0.2, color='blue', label=f'Min-max range (top-{top_n})')
    
    # Overall average line
    overall_avg = stats['avg_latency_us'].mean()
    ax.axhline(y=overall_avg, color='black', linestyle='--', 
               linewidth=1.5, label=f'Overall average: {overall_avg:.1f} µs')
    
    # Information about used latencies
    avg_used = stats['latencies_used'].mean()
    ax.text(0.02, 0.98, f'Latencies used per group: {avg_used:.0f}',
            transform=ax.transAxes, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    # Add fall information if available
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
            ax.text(0.98, 0.98, f'Falls in session: {falls_count}',
                    transform=ax.transAxes, verticalalignment='top', 
                    horizontalalignment='right',
                    bbox=dict(boxstyle='round', facecolor='lightcoral', alpha=0.5))
    
    ax.set_xlabel('Group Number')
    ax.set_ylabel('Latency (µs)')
    ax.set_title(f'Latency Analysis (top-{top_n} worst per group)' + 
                 (f' (session {session_id})' if session_id else ''))
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    
    plt.tight_layout()
    
    if output:
        plt.savefig(output, dpi=150)
        print(f"✓ Plot saved: {output}")
    else:
        plt.show()

def plot_jitter(db_path: str, session_id: int = None, output: str = None) -> None:
    """
    Generate jitter plot over groups.
    
    Args:
        db_path: Path to SQLite database
        session_id: Optional session ID to filter data
        output: Output file path for saving the plot
    """
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
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    if df.empty:
        print("No data to display")
        return
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    groups = df['group_index']
    
    ax.plot(groups, df['jitter_us'], 'g-', linewidth=2, 
            label='Jitter (standard deviation)')
    
    overall_avg = df['jitter_us'].mean()
    ax.axhline(y=overall_avg, color='black', linestyle='--', 
               linewidth=1.5, label=f'Overall average: {overall_avg:.1f} µs')
    
    ax.set_xlabel('Group Number')
    ax.set_ylabel('Jitter (µs)')
    ax.set_title(f'Jitter Analysis' + 
                 (f' (session {session_id})' if session_id else ''))
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    
    plt.tight_layout()
    
    if output:
        plt.savefig(output, dpi=150)
        print(f"✓ Plot saved: {output}")
    else:
        plt.show()

def show_fall_details(db_path: str, session_id: int = None, 
                     limit: int = 20, log_to_file: bool = True) -> None:
    """
    Display detailed information about falls and recoveries.
    
    Args:
        db_path: Path to SQLite database
        session_id: Optional session ID to filter data
        limit: Maximum number of events to display
        log_to_file: Whether to save output to session log file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    query = '''
        SELECT 
            id,
            session_id,
            event_type,
            event_time,
            event_time_us,
            time_since_start_us,
            last_group_index,
            details
        FROM system_events
    '''
    params = []
    
    if session_id is not None:
        query += ' WHERE session_id = ?'
        params.append(session_id)
    
    query += ' ORDER BY id DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query, params)
    events = cursor.fetchall()
    conn.close()
    
    if not events:
        print("No events in database")
        return
    
    # Prepare output string
    output_lines = []
    output_lines.append("\n" + "="*120)
    output_lines.append(f"{'ID':<6} {'Session':<12} {'Type':<15} {'Time':<20} {'Since start(µs)':<18} {'Last group':<12} {'Details'}")
    output_lines.append("-"*120)
    
    for event in events:
        event_id, sess_id, e_type, e_time, e_time_us, time_since, last_group, details = event
        
        # Format event type
        if e_type == 'fall':
            type_str = "⚠️ FALL"
        elif e_type == 'recovery':
            type_str = "✅ RECOVERY"
        else:
            type_str = e_type
        
        # Format time
        if e_time:
            try:
                e_time_obj = datetime.fromisoformat(e_time.replace('T', ' '))
                time_str = e_time_obj.strftime('%Y-%m-%d %H:%M:%S')
            except:
                time_str = e_time[:19]
        else:
            time_str = "N/A"
        
        output_lines.append(f"{event_id:<6} {sess_id:<12} {type_str:<15} {time_str:<20} {time_since:<18,} {last_group:<12} {details}")
    
    output_lines.append("="*120)
    
    # Print to console
    for line in output_lines:
        print(line)
    
    # Log to file if requested and session_id is specified
    if log_to_file and session_id:
        logger = setup_session_logging(session_id)
        for line in output_lines:
            logger.info(line)
        print(f"\n✓ Events logged to logs/session_{session_id}.log")

def list_sessions(db_path: str) -> None:
    """
    Display list of all sessions with basic statistics.
    
    Args:
        db_path: Path to SQLite database
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
            MIN(l.latency_us) as min_latency,
            MAX(l.latency_us) as max_latency,
            (SELECT COUNT(*) FROM system_events e 
             WHERE e.session_id = g.session_id AND e.event_type = 'fall') as falls,
            (SELECT COUNT(*) FROM system_events e 
             WHERE e.session_id = g.session_id AND e.event_type = 'recovery') as recoveries
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
    print(f"{'Session ID':<15} {'First':<20} {'Last':<20} {'Groups':<8} {'Avg Latency':<12} {'Avg Jitter':<12} {'Falls':<8} {'Rec':<8} {'Status'}")
    print("-"*130)
    
    for sess in sessions:
        sess_id, first, last, groups, jitter, latency, min_lat, max_lat, falls, recs = sess
        
        # Session status
        if falls == 0:
            status = "✅"
        elif falls == recs:
            status = "⚠️"
        else:
            status = "❌"
        
        print(f"{sess_id:<15} {first[:19]:<20} {last[:19]:<20} {groups:<8} {latency:<12.2f} {jitter:<12.2f} {falls:<8} {recs:<8} {status}")
    
    print("="*130)

def show_session_stats(db_path: str, session_id: int = None) -> None:
    """
    Display detailed statistics for specific session or all sessions.
    
    Args:
        db_path: Path to SQLite database
        session_id: Optional session ID for detailed view
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    if session_id:
        cursor.execute('''
            SELECT 
                g.session_id,
                COUNT(DISTINCT g.id) as groups,
                COUNT(l.id) as latencies,
                ROUND(AVG(g.jitter_us), 2) as avg_jitter,
                ROUND(AVG(l.latency_us), 2) as avg_latency,
                MIN(l.latency_us) as min_lat,
                MAX(l.latency_us) as max_lat,
                MIN(g.pc_timestamp_us) as start_time_us,
                MAX(g.pc_timestamp_us) as end_time_us,
                (SELECT COUNT(*) FROM system_events e 
                 WHERE e.session_id = g.session_id AND e.event_type = 'fall') as falls,
                (SELECT COUNT(*) FROM system_events e 
                 WHERE e.session_id = g.session_id AND e.event_type = 'recovery') as recoveries
            FROM groups g
            LEFT JOIN latencies l ON g.id = l.group_id
            WHERE g.session_id = ?
            GROUP BY g.session_id
        ''', (session_id,))
    else:
        cursor.execute('''
            SELECT 
                g.session_id,
                COUNT(DISTINCT g.id) as groups,
                COUNT(l.id) as latencies,
                ROUND(AVG(g.jitter_us), 2) as avg_jitter,
                ROUND(AVG(l.latency_us), 2) as avg_latency,
                MIN(l.latency_us) as min_lat,
                MAX(l.latency_us) as max_lat,
                MIN(g.pc_timestamp_us) as start_time_us,
                MAX(g.pc_timestamp_us) as end_time_us,
                (SELECT COUNT(*) FROM system_events e 
                 WHERE e.session_id = g.session_id AND e.event_type = 'fall') as falls,
                (SELECT COUNT(*) FROM system_events e 
                 WHERE e.session_id = g.session_id AND e.event_type = 'recovery') as recoveries
            FROM groups g
            LEFT JOIN latencies l ON g.id = l.group_id
            GROUP BY g.session_id
            ORDER BY g.session_id DESC
        ''')
    
    rows = cursor.fetchall()
    
    if not rows:
        print("No data")
        conn.close()
        return
    
    print("\n" + "="*130)
    print(f"{'Session':<12} {'Groups':<8} {'Latencies':<10} {'Avg Latency':<12} {'Avg Jitter':<12} {'Min/Max':<18} {'Duration(s)':<12} {'Falls':<8} {'Rec':<8} {'Status':<10}")
    print("-"*130)
    
    for row in rows:
        session_id_val, groups, latencies, avg_jitter, avg_latency, min_lat, max_lat, start_us, end_us, falls, recs = row
        
        # Session duration in seconds
        if start_us and end_us:
            duration_sec = (end_us - start_us) / 1_000_000
            duration_str = f"{duration_sec:.1f}"
        else:
            duration_str = "N/A"
        
        # Session status
        if falls == 0:
            status = "✅ OK"
        elif falls == recs:
            status = "⚠️ Had falls"
        else:
            status = "❌ Unresolved"
        
        latency_range = f"{min_lat:.0f}/{max_lat:.0f}"
        
        print(f"{session_id_val:<12} {groups:<8} {latencies:<10} {avg_latency:<12.2f} {avg_jitter:<12.2f} {latency_range:<18} {duration_str:<12} {falls:<8} {recs:<8} {status:<10}")
    
    print("="*130)
    conn.close()

def main():
    """Main entry point with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description='Arduino Data Visualization and Analysis Tool',
        epilog='For more information, see README.md'
    )
    parser.add_argument('db', help='Path to SQLite database')
    parser.add_argument('--session', type=int, help='Session ID (if not specified, all sessions)')
    parser.add_argument('--output', '-o', help='Save plot to file instead of displaying')
    parser.add_argument('--top', type=int, default=25, 
                       help='Number of worst latencies to analyze (1-25, default: 25)')
    parser.add_argument('--limit', type=int, default=20,
                       help='Limit entries for events list (default: 20)')
    parser.add_argument('--no-log', action='store_true',
                       help='Disable logging to file (console only)')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Latency plot
    parser_latency = subparsers.add_parser('latency', help='Plot latency over groups')
    
    # Jitter plot
    parser_jitter = subparsers.add_parser('jitter', help='Plot jitter over groups')
    
    # Fall details
    parser_falls = subparsers.add_parser('falls', help='Show detailed fall/recovery information')
    
    # Session list
    subparsers.add_parser('sessions', help='List all sessions')
    
    # Session statistics
    subparsers.add_parser('stats', help='Show session statistics')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.db):
        print(f"Error: Database file {args.db} not found")
        return
    
    try:
        if args.command == 'sessions':
            list_sessions(args.db)
        
        elif args.command == 'stats':
            show_session_stats(args.db, args.session)
        
        elif args.command == 'falls':
            show_fall_details(args.db, args.session, args.limit, not args.no_log)
        
        elif args.command == 'latency':
            plot_latency_over_time(args.db, args.session, args.output, args.top)
        
        elif args.command == 'jitter':
            plot_jitter(args.db, args.session, args.output)
        
        else:
            print("Please specify a command. Available commands:")
            print("  latency   - plot latency over groups")
            print("  jitter    - plot jitter over groups")
            print("  falls     - show detailed fall/recovery information")
            print("  stats     - show session statistics")
            print("  sessions  - list all sessions")
            print("\nFor more information, see README.md")
            
    except ValueError as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()