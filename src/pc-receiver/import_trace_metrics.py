#!/usr/bin/env python3
"""Import rt-supervisor group trace metrics from Prometheus into SQLite."""

import argparse
import sqlite3
import time

import database as db
from prometheus_client import PrometheusClient


def _metric_key(labels):
    return (
        labels.get('session_id'),
        labels.get('group_index'),
        labels.get('host'),
        labels.get('stage'),
    )


def _session_window(db_path, session_id):
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT MIN(CASE WHEN event_type = 'start' THEN event_time_us END),
                   MAX(CASE WHEN event_type = 'stop' THEN event_time_us END)
            FROM events
            WHERE session_id = ?
            """,
            (session_id,),
        )
        start_us, stop_us = cur.fetchone()

    end = int(time.time())
    start = end - 3600
    if start_us:
        start = max(0, int(start_us / 1_000_000) - 60)
    if stop_us:
        end = int(stop_us / 1_000_000) + 300
    else:
        end += 300
    return start, end


def _range_items(client, query, start, end):
    data = client.query_range(query, start, end, step='30s')
    for item in data.get('result', []):
        values = item.get('values') or []
        if not values:
            continue
        yield {
            'metric': item.get('metric', {}),
            'value': values[-1],
        }


def import_trace_metrics(db_path, prometheus_url, session_id):
    db.init_database(db_path)
    client = PrometheusClient(prometheus_url=prometheus_url, timeout=10)

    records = {}
    stage_query = f'rt_trace_stage_us{{session_id="{session_id}"}}'
    count_query = f'rt_trace_stage_count{{session_id="{session_id}"}}'
    start, end = _session_window(db_path, session_id)

    for item in _range_items(client, stage_query, start, end):
        labels = item.get('metric', {})
        key = _metric_key(labels)
        if None in key:
            continue
        record = records.setdefault(key, {
            'session_id': key[0],
            'group_index': key[1],
            'host': key[2],
            'stage': key[3],
        })
        stat = labels.get('stat')
        if stat in ('min', 'avg', 'max'):
            record[f'{stat}_us'] = float(item.get('value', [0, 0])[1])

    for item in _range_items(client, count_query, start, end):
        labels = item.get('metric', {})
        key = _metric_key(labels)
        if None in key:
            continue
        record = records.setdefault(key, {
            'session_id': key[0],
            'group_index': key[1],
            'host': key[2],
            'stage': key[3],
        })
        record['count'] = int(float(item.get('value', [0, 0])[1]))

    for record in records.values():
        db.save_trace_group_metric(db_path, record)

    return len(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('db', help='SQLite database path')
    parser.add_argument('session_id', type=int)
    parser.add_argument('--prometheus-url', default='http://localhost:9090')
    args = parser.parse_args()

    count = import_trace_metrics(args.db, args.prometheus_url, args.session_id)
    print(f'Imported trace metrics: {count}')


if __name__ == '__main__':
    main()
