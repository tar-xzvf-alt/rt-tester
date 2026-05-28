#!/usr/bin/env python3
"""
Merge all .db files from tests/results_*/ into one database.

Usage:
    python3 src/pc-receiver/merge_databases.py tests merged.db

The script:
  1. Creates merged.db with the full schema
  2. Copies groups (remapping ids), latencies (remapping group_id),
     soc_metrics, and events from each source DB
  3. Prints summary: sessions per board, source DB -> session mapping
"""

import sqlite3
import os
import sys
import glob
from collections import defaultdict


SCHEMA = '''
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
);

CREATE TABLE IF NOT EXISTS latencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER,
    latency_us INTEGER,
    rank_in_group INTEGER,
    FOREIGN KEY (group_id) REFERENCES groups (id)
);

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
    duration_ms REAL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    event_type TEXT,
    event_time TEXT,
    event_time_us INTEGER,
    time_since_start_us INTEGER,
    group_index INTEGER,
    details TEXT
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
'''


def init_merged_db(db_path):
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=OFF")
    return conn


def find_db_files(results_dir):
    pattern = os.path.join(results_dir, "results_*", "*.db")
    return sorted(glob.glob(pattern))


def copy_table(merged, src, table, columns, extra_where=""):
    """Copy rows from src to merged, skipping 'id' column (auto-generated)."""
    cols = [c for c in columns if c != 'id']
    cols_str = ", ".join(cols)
    ph = ", ".join(["?"] * len(cols))
    query = f"SELECT {cols_str} FROM {table} {extra_where} ORDER BY id"
    try:
        rows = src.execute(query).fetchall()
    except sqlite3.OperationalError as e:
        print(f"  Warning: {e}")
        return {}
    for row in rows:
        merged.execute(f"INSERT OR IGNORE INTO {table} ({cols_str}) VALUES ({ph})", row)


def merge_all(results_dir, output_db):
    db_files = find_db_files(results_dir)
    if not db_files:
        print(f"No .db files found in {results_dir}/results_*/")
        return

    print(f"Found {len(db_files)} database(s):")
    for f in db_files:
        print(f"  {f}")

    merged = init_merged_db(output_db)
    print(f"\nCreated {output_db}")

    session_sources = defaultdict(list)

    for db_path in db_files:
        print(f"\n--- {db_path} ---")
        src = sqlite3.connect(db_path)
        src.execute("PRAGMA foreign_keys=OFF")

        # Get table info
        def table_has_columns(conn, table, cols):
            try:
                existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
                return all(c in existing for c in cols)
            except sqlite3.OperationalError:
                return False

        groups_cols = ['session_id', 'group_index', 'pc_timestamp',
                       'pc_timestamp_us', 'arduino_timestamp', 'jitter_us',
                       'delay_us', 'measurements_per_group', 'worst_count',
                       'target_board', 'target_kernel', 'target_stress']

        latencies_cols = ['group_id', 'latency_us', 'rank_in_group']
        soc_cols = ['session_id', 'group_index', 'pc_timestamp', 'cpu_percent',
                    'memory_percent', 'cpu_max', 'mem_max', 'cpu_avg',
                    'mem_avg', 'samples_in_group', 'duration_ms']
        events_cols = ['session_id', 'event_type', 'event_time', 'event_time_us',
                       'time_since_start_us', 'group_index', 'details']

        # Build old_id → new_id mapping for groups
        id_map = {}
        if table_has_columns(src, 'groups', groups_cols):
            rows = src.execute("SELECT id, " + ", ".join(groups_cols) + " FROM groups ORDER BY id").fetchall()
            for row in rows:
                old_id = row[0]
                vals = row[1:]
                try:
                    cur = merged.execute(
                        f"INSERT INTO groups ({', '.join(groups_cols)}) VALUES "
                        f"({', '.join(['?']*len(groups_cols))})", vals)
                    id_map[old_id] = cur.lastrowid
                except sqlite3.IntegrityError:
                    # duplicate (session_id, group_index) — find existing
                    existing = merged.execute(
                        "SELECT id FROM groups WHERE session_id=? AND group_index=?",
                        (vals[0], vals[1])).fetchone()
                    if existing:
                        id_map[old_id] = existing[0]
            merged.commit()

        # Latencies with remapped group_id
        if table_has_columns(src, 'latencies', latencies_cols):
            rows = src.execute("SELECT group_id, latency_us, rank_in_group FROM latencies ORDER BY id").fetchall()
            copied = 0
            for row in rows:
                new_gid = id_map.get(row[0])
                if new_gid is None:
                    continue
                merged.execute(
                    "INSERT OR IGNORE INTO latencies (group_id, latency_us, rank_in_group) VALUES (?,?,?)",
                    (new_gid, row[1], row[2]))
                copied += 1
            merged.commit()
            print(f"  latencies: {copied} rows")

        # soc_metrics (no foreign keys)
        if table_has_columns(src, 'soc_metrics', soc_cols):
            copy_table(merged, src, 'soc_metrics', ['id'] + soc_cols)
            merged.commit()
            print(f"  soc_metrics: copied")

        # events
        if table_has_columns(src, 'events', events_cols):
            copy_table(merged, src, 'events', ['id'] + events_cols)
            merged.commit()
            print(f"  events: copied")

        # Track sessions
        try:
            sessions = src.execute("SELECT DISTINCT session_id, target_board, target_kernel, target_stress FROM groups").fetchall()
        except sqlite3.OperationalError:
            sessions = src.execute("SELECT DISTINCT session_id FROM groups").fetchall()
        for s in sessions:
            sid = s[0]
            board = s[1] if len(s) > 1 and s[1] else '?'
            session_sources[sid].append((db_path, board))

        src.close()

    # Summary
    print("\n" + "=" * 80)
    print(f"MERGE COMPLETE: {len(session_sources)} sessions total")
    print("=" * 80)

    grouped = defaultdict(list)
    for sid, sources in session_sources.items():
        board = sources[0][1]
        grouped[board].append(sid)

    for board in sorted(grouped):
        sids = grouped[board]
        print(f"\n{board} ({len(sids)} sessions)")
        for sid in sorted(sids):
            sources = ", ".join(os.path.basename(s[0]) for s in session_sources[sid])
            # Count groups in merged DB
            count = merged.execute("SELECT COUNT(*) FROM groups WHERE session_id=?", (sid,)).fetchone()[0]
            print(f"  {sid}: {count} groups (from {sources})")

    merged.execute("PRAGMA foreign_keys=ON")

    # Match PNG files by session_id prefix
    png_pattern = os.path.join(results_dir, "results_*", "*.png")
    png_files = sorted(glob.glob(png_pattern))
    png_by_session = defaultdict(list)
    for png in png_files:
        basename = os.path.basename(png)
        parts = basename.split("_", 1)
        if parts[0].isdigit():
            png_by_session[int(parts[0])].append(png)

    print("\n--- Existing PNG graphs ---")
    matched = 0
    for sid in sorted(session_sources):
        if sid in png_by_session:
            matched += 1
            print(f"  Session {sid}:")
            for p in png_by_session[sid]:
                print(f"    {os.path.basename(p)}")
    if matched == 0:
        print("  (no pre-existing PNG graphs found)")
    else:
        print(f"\n  {matched} sessions have pre-existing PNG graphs")

    merged.close()
    print(f"\nMerged database: {output_db}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: merge_databases.py <results_dir> <output.db>")
        print("Example: merge_databases.py tests merged.db")
        sys.exit(1)
    merge_all(sys.argv[1], sys.argv[2])
