#!/usr/bin/env python3
"""
Скрипт для построения графиков по данным из SQLite.
Запускается отдельно, может рисовать разные представления.
"""

import sqlite3
import argparse
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from datetime import datetime
import pandas as pd
import os

def plot_latency_over_time(db_path, session_id=None, output=None):
    """График задержки по времени (по группам)"""
    conn = sqlite3.connect(db_path)
    
    query = '''
        SELECT group_index, avg_latency_us, min_latency_us, max_latency_us
        FROM measurements
    '''
    params = []
    
    if session_id is not None:
        query += ' WHERE session_id = ?'
        params.append(session_id)
    
    query += ' ORDER BY group_index'
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    if df.empty:
        print("Нет данных для отображения")
        return
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    groups = df['group_index']
    
    # Линия средних значений
    ax.plot(groups, df['avg_latency_us'], 'b-', linewidth=2, label='Средняя задержка')
    
    # Зона мин-макс
    ax.fill_between(groups, df['min_latency_us'], df['max_latency_us'], 
                    alpha=0.2, color='blue', label='Диапазон мин-макс')
    
    # Горизонтальная линия общего среднего
    overall_avg = df['avg_latency_us'].mean()
    ax.axhline(y=overall_avg, color='black', linestyle='--', 
               linewidth=1.5, label=f'Общее среднее: {overall_avg:.1f} мкс')
    
    ax.set_xlabel('Номер группы')
    ax.set_ylabel('Задержка (мкс)')
    ax.set_title(f'Анализ задержки' + (f' (сессия {session_id})' if session_id else ''))
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    
    plt.tight_layout()
    
    if output:
        plt.savefig(output, dpi=150)
        print(f"✓ График сохранён: {output}")
    else:
        plt.show()

def plot_jitter(db_path, session_id=None, output=None):
    """График джиттера"""
    conn = sqlite3.connect(db_path)
    
    query = '''
        SELECT group_index, avg_jitter_us
        FROM measurements
    '''
    params = []
    
    if session_id is not None:
        query += ' WHERE session_id = ?'
        params.append(session_id)
    
    query += ' ORDER BY group_index'
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    if df.empty:
        print("Нет данных для отображения")
        return
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    groups = df['group_index']
    
    ax.plot(groups, df['avg_jitter_us'], 'g-', linewidth=2, label='Средний джиттер')
    
    overall_avg = df['avg_jitter_us'].mean()
    ax.axhline(y=overall_avg, color='black', linestyle='--', 
               linewidth=1.5, label=f'Общее среднее: {overall_avg:.1f} мкс')
    
    ax.set_xlabel('Номер группы')
    ax.set_ylabel('Джиттер (мкс)')
    ax.set_title(f'Анализ джиттера' + (f' (сессия {session_id})' if session_id else ''))
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    
    plt.tight_layout()
    
    if output:
        plt.savefig(output, dpi=150)
        print(f"✓ График сохранён: {output}")
    else:
        plt.show()

def plot_histogram(db_path, session_id=None, output=None, bins=50):
    """Гистограмма распределения задержек"""
    conn = sqlite3.connect(db_path)
    
    # Для гистограммы нам нужны все средние значения по группам
    query = '''
        SELECT avg_latency_us
        FROM measurements
    '''
    params = []
    
    if session_id is not None:
        query += ' WHERE session_id = ?'
        params.append(session_id)
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    if df.empty:
        print("Нет данных для отображения")
        return
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    ax.hist(df['avg_latency_us'], bins=bins, alpha=0.7, color='blue', edgecolor='black')
    
    ax.axvline(x=df['avg_latency_us'].mean(), color='red', linestyle='--', 
               linewidth=2, label=f'Среднее: {df["avg_latency_us"].mean():.1f} мкс')
    ax.axvline(x=df['avg_latency_us'].median(), color='green', linestyle=':', 
               linewidth=2, label=f'Медиана: {df["avg_latency_us"].median():.1f} мкс')
    
    ax.set_xlabel('Задержка (мкс)')
    ax.set_ylabel('Частота')
    ax.set_title('Распределение средних задержек по группам')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if output:
        plt.savefig(output, dpi=150)
        print(f"✓ Гистограмма сохранена: {output}")
    else:
        plt.show()

def list_sessions(db_path):
    """Список всех сессий в БД"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            session_id,
            MIN(created_at) as first_seen,
            MAX(created_at) as last_seen,
            COUNT(*) as groups_count,
            AVG(avg_latency_us) as avg_latency
        FROM measurements
        GROUP BY session_id
        ORDER BY first_seen DESC
    ''')
    
    sessions = cursor.fetchall()
    conn.close()
    
    if not sessions:
        print("Нет сессий в базе данных")
        return
    
    print("\n📋 СЕССИИ В БАЗЕ ДАННЫХ")
    print("="*80)
    print(f"{'ID сессии':<15} {'Первая':<20} {'Последняя':<20} {'Групп':<8} {'Ср. задержка':<12}")
    print("-"*80)
    
    for sess in sessions:
        print(f"{sess[0]:<15} {sess[1][:19]:<20} {sess[2][:19]:<20} {sess[3]:<8} {sess[4]:.2f} мкс")
    
    print("="*80)

def export_to_csv(db_path, session_id=None, output=None):
    """Экспорт данных в CSV"""
    conn = sqlite3.connect(db_path)
    
    query = '''
        SELECT 
            session_id,
            group_index,
            created_at as timestamp,
            avg_latency_us,
            min_latency_us,
            max_latency_us,
            avg_jitter_us
        FROM measurements
    '''
    params = []
    
    if session_id is not None:
        query += ' WHERE session_id = ?'
        params.append(session_id)
    
    query += ' ORDER BY session_id, group_index'
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    if df.empty:
        print("Нет данных для экспорта")
        return
    
    if output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if session_id:
            output = f"arduino_data_session_{session_id}_{timestamp}.csv"
        else:
            output = f"arduino_data_all_{timestamp}.csv"
    
    df.to_csv(output, index=False)
    print(f"✓ Данные экспортированы в {output}")

def main():
    parser = argparse.ArgumentParser(description='Визуализация данных с Arduino')
    parser.add_argument('db', help='Путь к SQLite БД')
    parser.add_argument('--session', type=int, help='ID сессии (если не указан, все сессии)')
    parser.add_argument('--output', '-o', help='Сохранить в файл вместо отображения')
    
    subparsers = parser.add_subparsers(dest='command', help='Тип графика')
    
    # График задержки
    parser_latency = subparsers.add_parser('latency', help='График задержки по группам')
    
    # График джиттера
    parser_jitter = subparsers.add_parser('jitter', help='График джиттера по группам')
    
    # Гистограмма
    parser_hist = subparsers.add_parser('hist', help='Гистограмма распределения')
    parser_hist.add_argument('--bins', type=int, default=50, help='Количество корзин')
    
    # Список сессий
    subparsers.add_parser('sessions', help='Список всех сессий')
    
    # Экспорт в CSV
    parser_csv = subparsers.add_parser('csv', help='Экспорт в CSV')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.db):
        print(f"Ошибка: файл БД {args.db} не найден")
        return
    
    if args.command == 'sessions':
        list_sessions(args.db)
    
    elif args.command == 'csv':
        export_to_csv(args.db, args.session, args.output)
    
    elif args.command == 'latency':
        plot_latency_over_time(args.db, args.session, args.output)
    
    elif args.command == 'jitter':
        plot_jitter(args.db, args.session, args.output)
    
    elif args.command == 'hist':
        plot_histogram(args.db, args.session, args.output, args.bins)
    
    else:
        print("Укажите команду: latency, jitter, hist, sessions, csv")
        print("Пример: python plot_arduino_data.py arduino_data.db latency --session 123456")

if __name__ == "__main__":
    main()