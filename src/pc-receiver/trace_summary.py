#!/usr/bin/env python3
"""Print rt-supervisor trace breakdown saved in SQLite."""

import argparse
import sqlite3


def latest_session(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT session_id
        FROM trace_group_metrics
        GROUP BY session_id
        ORDER BY MAX(id) DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    return row[0] if row else None


def print_summary(db_path, session_id, host=None):
    with sqlite3.connect(db_path) as conn:
        if session_id is None:
            session_id = latest_session(conn)
            if session_id is None:
                raise SystemExit('No trace metrics found')

        cur = conn.cursor()
        if host:
            cur.execute(
                """
                SELECT host, stage, COUNT(*) AS groups,
                       AVG(avg_us), MIN(min_us), MAX(max_us), SUM(count)
                FROM trace_group_metrics
                WHERE session_id = ? AND host = ?
                GROUP BY host, stage
                ORDER BY host, stage
                """,
                (session_id, host),
            )
        else:
            cur.execute(
                """
                SELECT host, stage, COUNT(*) AS groups,
                       AVG(avg_us), MIN(min_us), MAX(max_us), SUM(count)
                FROM trace_group_metrics
                WHERE session_id = ?
                GROUP BY host, stage
                ORDER BY host, stage
                """,
                (session_id,),
            )
        rows = cur.fetchall()

    if not rows:
        raise SystemExit(f'No trace metrics found for session {session_id}')

    print(f'Trace summary for session {session_id}')
    print(
        f'{"host":<12} {"stage":<18} {"groups":>6} {"samples":>8} '
        f'{"avg_us":>12} {"min_us":>12} {"max_us":>12}'
    )
    print('-' * 88)
    for host, stage, groups, avg_us, min_us, max_us, samples in rows:
        print(
            f'{host:<12} {stage:<18} {groups:>6} {samples:>8} '
            f'{avg_us:>12.2f} {min_us:>12.2f} {max_us:>12.2f}'
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('db', help='SQLite database path')
    parser.add_argument('--session-id', type=int, help='Session ID to summarize')
    parser.add_argument('--host', help='filter by trace host label')
    args = parser.parse_args()

    print_summary(args.db, args.session_id, args.host)


if __name__ == '__main__':
    main()
