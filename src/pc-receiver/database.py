"""
Database operations for Arduino collector.
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Tuple, Any
from config import DEFAULT_DB_PATH


def init_database(db_path):
    """Initialize database with all tables."""

    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

   # Groups information table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            group_index INTEGER,
            pc_timestamp TEXT,
            pc_timestamp_us INTEGER,
            arduino_timestamp INTEGER,
            jitter_us REAL,
            delay_us INTEGER,
            measurements_per_group INTEGER,
            worst_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, group_index)
        )
    ''')
    
    # Individual latencies table (25 worst per group)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS latencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            latency_us INTEGER,
            rank_in_group INTEGER,  -- 1 = largest, 25 = 25th largest
            FOREIGN KEY (group_id) REFERENCES groups (id) ON DELETE CASCADE
        )
    ''')
    
    # System events table (falls/recoveries)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            event_type TEXT,  -- 'fall' or 'recovery'
            event_time TEXT,
            event_time_us INTEGER,
            time_since_start_us INTEGER,
            last_group_index INTEGER,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    
    # SoC metrics table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS soc_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            group_index INTEGER,
            pc_timestamp TEXT,
            cpu_percent REAL,
            memory_percent REAL,
            cpu_max REAL,
            mem_max REAL,
            cpu_avg REAL,
            mem_avg REAL,
            samples_in_group INTEGER,
            duration_ms REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Events table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            event_type TEXT,
            pc_timestamp TEXT,
            time_since_start_us INTEGER,
            group_index INTEGER,
            details TEXT
        )
    ''')
    
    # Indexes
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_groups_session 
        ON groups(session_id, group_index)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_latencies_group 
        ON latencies(group_id)
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id)')
    
    conn.commit()
    conn.close()


def save_group_data(db_path: str, data: dict, current_time_us: int) -> Optional[int]:
    """
    Save group data and worst latencies to database.
    
    Args:
        db_path: Path to SQLite database
        data: JSON data from Arduino
        current_time_us: Current time in microseconds
    
    Returns:
        group_id if successful, None otherwise
    """
    if "group_index" not in data or "worst_latencies_us" not in data:
        return None
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    params = data.get('parameters', {})
    
    # Insert group information
    cursor.execute('''
        INSERT OR REPLACE INTO groups 
        (session_id, group_index, pc_timestamp, pc_timestamp_us, arduino_timestamp,
         jitter_us, delay_us, measurements_per_group, worst_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('session_id', 0),
        data['group_index'],
        datetime.now().isoformat(),
        current_time_us,
        data.get('timestamp', 0),
        data.get('jitter_us', 0),
        params.get('delay_us', 0),
        params.get('measurements_per_group', 0),
        data.get('worst_count', 25)
    ))
    
    # Get inserted group ID
    group_id = cursor.lastrowid
    
    # Insert 25 worst latencies
    worst_latencies = data.get('worst_latencies_us', [])
    for rank, latency in enumerate(worst_latencies, 1):
        cursor.execute('''
            INSERT INTO latencies (group_id, latency_us, rank_in_group)
            VALUES (?, ?, ?)
        ''', (group_id, latency, rank))
    
    conn.commit()
    conn.close()
    
    return group_id


def save_fall_event(db_path: str, session_id: int, event_type: str, 
                   last_group_index: int, details: str = "",
                   start_command_time_us: int = 0) -> None:
    """
    Save fall or recovery event to database.
    
    Args:
        db_path: Path to SQLite database
        session_id: Current session ID
        event_type: 'fall' or 'recovery'
        last_group_index: Last received group index
        details: Additional details
        start_command_time_us: START command time in microseconds
    """
    if session_id is None:
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    current_time_us = datetime.now().timestamp() * 1_000_000
    time_since_start_us = 0
    
    if start_command_time_us:
        time_since_start_us = int(current_time_us - start_command_time_us)
    
    cursor.execute('''
        INSERT INTO system_events 
        (session_id, event_type, event_time, event_time_us, 
         time_since_start_us, last_group_index, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        session_id,
        event_type,
        datetime.now().isoformat(),
        int(current_time_us),
        time_since_start_us,
        last_group_index,
        details
    ))
    
    conn.commit()
    conn.close()


def get_db_stats(db_path: str, session_id: Optional[int] = None) -> Tuple:
    """
    Get database statistics.
    
    Args:
        db_path: Path to SQLite database
        session_id: Optional session ID for filtering
    
    Returns:
        Tuple with statistics
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            COUNT(DISTINCT g.session_id) as sessions,
            COUNT(DISTINCT g.id) as total_groups,
            COUNT(l.id) as total_latencies,
            AVG(g.jitter_us) as avg_jitter,
            AVG(l.latency_us) as avg_latency,
            MIN(l.latency_us) as min_latency,
            MAX(l.latency_us) as max_latency
        FROM groups g
        LEFT JOIN latencies l ON g.id = l.group_id
    ''')
    
    row = cursor.fetchone()
    
    # Get fall statistics for current session
    if session_id:
        cursor.execute('''
            SELECT 
                COUNT(*) as falls,
                SUM(CASE WHEN event_type = 'recovery' THEN 1 ELSE 0 END) as recoveries
            FROM system_events
            WHERE session_id = ?
        ''', (session_id,))
        events_row = cursor.fetchone()
    else:
        events_row = None
    
    conn.close()
    
    return row, events_row


def get_recent_events(db_path: str, session_id: Optional[int], limit: int = 10) -> List[Tuple]:
    """
    Get recent events from database.
    
    Args:
        db_path: Path to SQLite database
        session_id: Session ID (if None, get from all sessions)
        limit: Maximum number of events
    
    Returns:
        List of event tuples
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    query = '''
        SELECT 
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
    
    return events


def save_soc_metrics_from_log(db_path, metrics):
    """
    Save SoC metrics parsed from log file to database.
    
    Args:
        db_path: Path to SQLite database
        metrics: Dictionary with parsed metrics
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO soc_metrics 
        (session_id, group_index, pc_timestamp, cpu_percent, memory_percent,
         cpu_max, mem_max, cpu_avg, mem_avg, samples_in_group, duration_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        metrics.get('session_id'),
        metrics.get('group_index'),
        datetime.now().isoformat(),
        metrics.get('cpu_avg'),  # используем среднее как основное значение
        metrics.get('mem_avg'),
        metrics.get('cpu_max'),
        metrics.get('mem_max'),
        metrics.get('cpu_avg'),
        metrics.get('mem_avg'),
        metrics.get('samples'),
        metrics.get('duration_ms')
    ))
    
    conn.commit()
    conn.close()