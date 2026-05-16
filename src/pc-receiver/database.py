"""
Database operations for Arduino collector with WAL mode and transactions.
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Tuple, Any
from contextlib import contextmanager
from config import DEFAULT_DB_PATH


class DatabaseManager:
    """
    Database manager with WAL mode and transaction support.
    """
    
    def __init__(self, db_path: str):
        """
        Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._ensure_directory()
    
    def _ensure_directory(self):
        """Ensure database directory exists."""
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
    
    @contextmanager
    def connection(self):
        """
        Context manager for database connections with WAL mode.
        
        Usage:
            with db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(...)
                conn.commit()
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute('PRAGMA journal_mode=WAL')  # Write-Ahead Logging
        conn.execute('PRAGMA synchronous=NORMAL')  # Good balance of safety and speed
        conn.execute('PRAGMA foreign_keys=ON')  # Enforce foreign key constraints
        
        try:
            yield conn
        finally:
            conn.close()
    
    @contextmanager
    def transaction(self):
        """
        Context manager for transactions.
        
        Usage:
            with db.transaction() as conn:
                # multiple operations
                # automatically commits on success, rolls back on exception
        """
        with self.connection() as conn:
            try:
                conn.execute('BEGIN TRANSACTION')
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """
        Execute a single query with auto-commit.
        
        Args:
            query: SQL query string
            params: Query parameters
        
        Returns:
            Cursor object
        """
        with self.connection() as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor
    
    def executemany(self, query: str, params_list: List[tuple]) -> int:
        """
        Execute multiple queries in a single transaction.
        
        Args:
            query: SQL query string
            params_list: List of parameter tuples
        
        Returns:
            Number of affected rows
        """
        with self.transaction() as conn:
            cursor = conn.executemany(query, params_list)
            return cursor.rowcount


# Global database manager instance
_db_manager = None


def get_db_manager(db_path: str = None) -> DatabaseManager:
    """
    Get or create database manager instance.
    
    Args:
        db_path: Path to SQLite database (required for first call)
    
    Returns:
        DatabaseManager instance
    """
    global _db_manager
    if _db_manager is None:
        if db_path is None:
            db_path = DEFAULT_DB_PATH
        _db_manager = DatabaseManager(db_path)
    return _db_manager


def init_database(db_path: str) -> None:
    """
    Initialize database with all tables.
    """
    db = get_db_manager(db_path)
    
    with db.transaction() as conn:
        cursor = conn.cursor()
        
        # Groups information table (updated with target info)
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
                target_board TEXT,
                target_kernel TEXT,
                target_stress TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, group_index)
            )
        ''')
        
        # Add columns if they don't exist (for existing databases)
        try:
            cursor.execute("ALTER TABLE groups ADD COLUMN target_board TEXT")
        except sqlite3.OperationalError:
            pass
        
        try:
            cursor.execute("ALTER TABLE groups ADD COLUMN target_kernel TEXT")
        except sqlite3.OperationalError:
            pass
        
        try:
            cursor.execute("ALTER TABLE groups ADD COLUMN target_stress TEXT")
        except sqlite3.OperationalError:
            pass
        
        # Individual latencies table (N  worst per group)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS latencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER,
                latency_us INTEGER,
                rank_in_group INTEGER,
                FOREIGN KEY (group_id) REFERENCES groups (id) ON DELETE CASCADE
            )
        ''')
        
        # Unified events table (replaces system_events and events)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                event_type TEXT,
                event_time TEXT,
                event_time_us INTEGER,
                time_since_start_us INTEGER,
                group_index INTEGER,
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
        
        # Indexes for performance
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_groups_session 
            ON groups(session_id, group_index)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_latencies_group 
            ON latencies(group_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_events_session 
            ON events(session_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_events_type 
            ON events(event_type, created_at)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_soc_session 
            ON soc_metrics(session_id)
        ''')
        
        # Version tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Check if migration needed
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_events'")
        old_table_exists = cursor.fetchone() is not None
        
        if old_table_exists:
            print("Migrating old events tables...")
            _migrate_events_tables(conn)
    
    print(f"Database initialized: {db_path}")
    print(f"  WAL mode: ENABLED")


def _migrate_events_tables(conn: sqlite3.Connection) -> None:
    """
    Migrate data from old system_events and events tables to new unified events table.
    """
    cursor = conn.cursor()
    
    # Check if system_events table has data
    cursor.execute("SELECT COUNT(*) FROM system_events")
    system_events_count = cursor.fetchone()[0]
    
    if system_events_count > 0:
        print(f"  Migrating {system_events_count} events from system_events...")
        cursor.execute('''
            INSERT INTO events 
            (session_id, event_type, event_time, event_time_us, 
             time_since_start_us, group_index, details)
            SELECT 
                session_id, 
                event_type, 
                event_time, 
                event_time_us,
                time_since_start_us, 
                last_group_index, 
                details
            FROM system_events
        ''')
    
    # Check if old events table exists and has data
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
    if cursor.fetchone():
        cursor.execute("SELECT COUNT(*) FROM events WHERE event_type NOT IN ('fall', 'recovery')")
        events_count = cursor.fetchone()[0]
        
        if events_count > 0:
            print(f"  Migrating {events_count} events from old events table...")
            cursor.execute('''
                INSERT INTO events 
                (session_id, event_type, event_time, time_since_start_us, group_index, details)
                SELECT 
                    session_id, 
                    event_type, 
                    pc_timestamp, 
                    time_since_start_us, 
                    group_index, 
                    details
                FROM events
                WHERE event_type NOT IN ('fall', 'recovery')
            ''')
    
    # Drop old tables
    cursor.execute("DROP TABLE IF EXISTS system_events")
    
    print("  Old tables dropped, migration complete")


def save_group_data(db_path: str, data: dict, current_time_us: int,
                    target_board: str = "unknown", target_kernel: str = "unknown",
                    target_stress: str = "off") -> Optional[int]:
    """
    Save group data and worst latencies to database using transaction.
    """
    if "group_index" not in data or "worst_latencies_us" not in data:
        return None
    
    db = get_db_manager(db_path)
    params = data.get('parameters', {})
    worst_latencies = data.get('worst_latencies_us', [])
    
    with db.transaction() as conn:
        cursor = conn.cursor()
        
        # Insert group information with target info
        cursor.execute('''
            INSERT OR REPLACE INTO groups 
            (session_id, group_index, pc_timestamp, pc_timestamp_us, arduino_timestamp,
             jitter_us, delay_us, measurements_per_group, worst_count,
             target_board, target_kernel, target_stress)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('session_id', 0),
            data['group_index'],
            datetime.now().isoformat(),
            current_time_us,
            data.get('timestamp', 0),
            data.get('jitter_us', 0),
            params.get('interval_us', 0),
            params.get('measurements_per_group', 0),
            data.get('worst_count', 125),
            target_board,
            target_kernel,
            target_stress
        ))
        
        # Get inserted group ID
        group_id = cursor.lastrowid
        
        # Insert worst latencies
        for rank, latency in enumerate(worst_latencies, 1):
            cursor.execute('''
                INSERT INTO latencies (group_id, latency_us, rank_in_group)
                VALUES (?, ?, ?)
            ''', (group_id, latency, rank))
    
    return group_id


def save_event(db_path: str, session_id: int, event_type: str, 
               group_index: int = None, details: str = "",
               start_command_time_us: int = 0) -> None:
    """
    Save an event to the unified events table.
    
    Args:
        db_path: Path to SQLite database
        session_id: Current session ID
        event_type: 'fall', 'recovery', 'start', 'stop', 'auto_stop'
        group_index: Associated group index (for fall/recovery)
        details: Additional details
        start_command_time_us: START command time in microseconds
    """
    if session_id is None:
        return
    
    db = get_db_manager(db_path)
    current_time_us = int(datetime.now().timestamp() * 1_000_000)
    time_since_start_us = 0
    
    if start_command_time_us:
        time_since_start_us = current_time_us - start_command_time_us
    
    with db.transaction() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO events 
            (session_id, event_type, event_time, event_time_us, 
             time_since_start_us, group_index, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            session_id,
            event_type,
            datetime.now().isoformat(),
            current_time_us,
            time_since_start_us,
            group_index,
            details
        ))


def save_fall_event(db_path: str, session_id: int, event_type: str, 
                   last_group_index: int, details: str = "",
                   start_command_time_us: int = 0) -> None:
    """
    Save fall or recovery event (wrapper for backward compatibility).
    """
    save_event(db_path, session_id, event_type, last_group_index, details, start_command_time_us)


def save_soc_metrics_from_log(db_path: str, metrics: dict) -> None:
    """
    Save SoC metrics parsed from log file to database.
    """
    db = get_db_manager(db_path)
    
    with db.transaction() as conn:
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
            metrics.get('cpu_avg'),      # primary value for main plots
            metrics.get('mem_avg'),
            metrics.get('cpu_max'),
            metrics.get('mem_max'),
            metrics.get('cpu_avg'),
            metrics.get('mem_avg'),
            metrics.get('samples'),
            metrics.get('duration_ms')
        ))


def save_session_start(db_path: str, session_id: int, auto_stop_groups: int = 0,
                       worst_count: int = 125, interval_us: int = 300,
                       target_board: str = "unknown", target_kernel: str = "unknown",
                       target_stress: str = "off") -> None:
    """
    Save session start event with measurement parameters and target info.
    """
    stress_status = "WITH STRESS" if target_stress == 'on' else "NO STRESS"
    details = (f"Board: {target_board}, Kernel: {target_kernel}, Stress: {stress_status}, "
               f"Auto-stop: {auto_stop_groups if auto_stop_groups else 'infinite'}, "
               f"worst_count: {worst_count}, interval: {interval_us} µs")
    save_event(db_path, session_id, "start", None, details)


def save_session_stop(db_path: str, session_id: int, groups_received: int, 
                      duration_us: int, reason: str = "user") -> None:
    """
    Save session stop event.
    """
    details = f"Groups: {groups_received}, Duration: {duration_us/1_000_000:.3f}s, Reason: {reason}"
    save_event(db_path, session_id, "stop", None, details)


def get_recent_events(db_path: str, session_id: Optional[int], limit: int = 10) -> List[Tuple]:
    """
    Get recent events from unified events table.
    """
    db = get_db_manager(db_path)
    
    with db.connection() as conn:
        cursor = conn.cursor()
        
        query = '''
            SELECT 
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
        
        query += ' ORDER BY id DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        return cursor.fetchall()


def get_db_stats(db_path: str, session_id: Optional[int] = None) -> Tuple:
    """
    Get database statistics.
    """
    db = get_db_manager(db_path)
    
    with db.connection() as conn:
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
        
        # Get event statistics for current session
        if session_id:
            cursor.execute('''
                SELECT 
                    COUNT(CASE WHEN event_type = 'fall' THEN 1 END) as falls,
                    COUNT(CASE WHEN event_type = 'recovery' THEN 1 END) as recoveries
                FROM events
                WHERE session_id = ?
            ''', (session_id,))
            events_row = cursor.fetchone()
        else:
            events_row = None
    
    return row, events_row


def vacuum(db_path: str) -> None:
    """
    Vacuum the database to reclaim space.
    """
    db = get_db_manager(db_path)
    
    with db.connection() as conn:
        print("Running VACUUM to reclaim space...")
        conn.execute("VACUUM")
        print("VACUUM complete")


def get_database_info(db_path: str) -> dict:
    """
    Get information about database state.
    """
    db = get_db_manager(db_path)
    info = {}
    
    with db.connection() as conn:
        cursor = conn.cursor()
        
        # Check WAL mode
        cursor.execute("PRAGMA journal_mode")
        info['journal_mode'] = cursor.fetchone()[0]
        
        # Check WAL file existence
        wal_path = db_path + "-wal"
        info['wal_exists'] = os.path.exists(wal_path)
        if info['wal_exists']:
            info['wal_size_bytes'] = os.path.getsize(wal_path)
        
        # Check database size
        info['db_size_bytes'] = os.path.getsize(db_path) if os.path.exists(db_path) else 0
        
        # Get table counts
        cursor.execute("SELECT COUNT(*) FROM groups")
        info['groups_count'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM events")
        info['events_count'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM soc_metrics")
        info['soc_metrics_count'] = cursor.fetchone()[0]
    
    return info