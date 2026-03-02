#!/usr/bin/env python3
"""
Демон сбора данных с Arduino в SQLite.
Запускается, подключается к Arduino и сохраняет все входящие группы в БД.
"""

import serial
import serial.tools.list_ports
import json
import time
import sqlite3
import argparse
import signal
import sys
from datetime import datetime
import os
import threading

class ArduinoCollector:
    def __init__(self, db_path="arduino_data.db", port=None, baudrate=115200):
        self.db_path = db_path
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False
        self.session_id = None
        self.groups_received = 0
        self.start_time = None
        
        # Инициализация БД
        self._init_database()
    
    def _init_database(self):
        """Создание таблицы в SQLite, если её нет"""
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                group_index INTEGER,
                pc_timestamp TEXT,
                arduino_timestamp INTEGER,
                avg_latency_us REAL,
                min_latency_us REAL,
                max_latency_us REAL,
                avg_jitter_us REAL,
                delay_us INTEGER,
                measurements_per_group INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Индекс для быстрого поиска по сессиям
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_session_group 
            ON measurements(session_id, group_index)
        ''')
        
        conn.commit()
        conn.close()
        
        print(f"✓ База данных инициализирована: {self.db_path}")
    
    def auto_detect_port(self):
        """Автоматическое определение порта Arduino"""
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            if 'Arduino' in port.description or 'ACM' in port.description:
                print(f"✓ Arduino найден на порту: {port.device}")
                return port.device
        
        print("✗ Arduino не найден. Доступные порты:")
        for port in ports:
            print(f"  {port.device}: {port.description}")
        return None
    
    def connect(self):
        """Подключение к Arduino"""
        if not self.port:
            self.port = self.auto_detect_port()
            if not self.port:
                return False
        
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2)  # Ждём инициализации Arduino
            
            # Очищаем буфер
            self.ser.reset_input_buffer()
            
            print(f"✓ Подключено к {self.port}")
            return True
        except Exception as e:
            print(f"✗ Ошибка подключения: {e}")
            return False
    
    def send_command(self, command):
        """Отправка команды Arduino"""
        if self.ser and self.ser.is_open:
            self.ser.write(f"{command}\n".encode('utf-8'))
            print(f"→ Команда: {command}")
    
    def read_json_message(self):
        """Чтение JSON-сообщения от Arduino"""
        if self.ser and self.ser.in_waiting > 0:
            try:
                line = self.ser.readline().decode('utf-8').strip()
                if line:
                    return json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                # Игнорируем некорректные сообщения
                pass
        return None
    
    def save_to_db(self, data):
        """Сохранение группы в SQLite"""
        if "group_index" not in data:
            return False
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        params = data.get('parameters', {})
        
        cursor.execute('''
            INSERT INTO measurements 
            (session_id, group_index, pc_timestamp, arduino_timestamp,
             avg_latency_us, min_latency_us, max_latency_us, avg_jitter_us,
             delay_us, measurements_per_group)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('session_id', 0),
            data['group_index'],
            datetime.now().isoformat(),
            data.get('timestamp', 0),
            data['avg_latency_us'],
            data['min_latency_us'],
            data['max_latency_us'],
            data['avg_jitter_us'],
            params.get('delay_us', 0),
            params.get('measurements_per_group', 0)
        ))
        
        conn.commit()
        conn.close()
        
        self.groups_received += 1
        return True
    
    def run(self):
        """Основной цикл сбора данных"""
        self.running = True
        self.start_time = time.time()
        
        print("\n" + "="*60)
        print("ДЕМОН СБОРА ДАННЫХ ARDUINO")
        print("="*60)
        print(f"БД: {self.db_path}")
        print("Команды: start, stop, status, exit")
        print("="*60)
        
        # Запускаем поток для чтения данных
        read_thread = threading.Thread(target=self._read_loop)
        read_thread.daemon = True
        read_thread.start()
        
        # Основной цикл обработки команд
        try:
            while self.running:
                cmd = input("\n> ").strip().lower()
                
                if cmd == "start":
                    self.send_command("START")
                    print("✓ Измерение запущено")
                
                elif cmd == "stop":
                    self.send_command("STOP")
                    collecting = False
                    print("✓ Измерение остановлено")
                
                elif cmd == "status":
                    elapsed = time.time() - self.start_time
                    hours = int(elapsed // 3600)
                    minutes = int((elapsed % 3600) // 60)
                    seconds = int(elapsed % 60)
                    
                    print(f"\n📊 Статистика:")
                    print(f"  Время работы: {hours:02d}:{minutes:02d}:{seconds:02d}")
                    print(f"  Получено групп: {self.groups_received}")
                    print(f"  Всего измерений: {self.groups_received * 1000}")
                    
                    if self.groups_received > 0:
                        rate = self.groups_received / elapsed
                        print(f"  Средняя скорость: {rate:.2f} групп/сек")
                        
                        # Получаем общую статистику из БД
                        self._show_db_stats()
                
                elif cmd == "exit":
                    print("Завершение работы...")
                    self.running = False
                
                elif cmd == "help":
                    print("\nДоступные команды:")
                    print("  start  - начать измерение")
                    print("  stop   - остановить измерение")
                    print("  status - показать статистику")
                    print("  exit   - выход")
                
                else:
                    print(f"Неизвестная команда: {cmd}")
        
        except KeyboardInterrupt:
            print("\n\nПрерывание пользователя")
        finally:
            self.running = False
            if self.ser:
                self.ser.close()
            print("✓ Соединение закрыто")
            print(f"✓ Данные сохранены в {self.db_path}")
    
    def _read_loop(self):
        """Фоновый поток чтения данных"""
        last_status = time.time()
        
        while self.running:
            msg = self.read_json_message()
            
            if msg:
                if "group_index" in msg:
                    self.save_to_db(msg)
                    
                    # Показываем прогресс раз в 10 групп
                    if self.groups_received % 10 == 0:
                        rate = 10 / (time.time() - last_status)
                        print(f"\r✓ Получено групп: {self.groups_received} "
                              f"({rate:.1f} групп/сек)", end="", flush=True)
                        last_status = time.time()
                
                elif "status" in msg:
                    status = msg.get('status')
                    if status == 'started':
                        self.session_id = msg.get('session_id')
                        print(f"\n✓ Новая сессия ID: {self.session_id}")
                    elif status == 'stopped':
                        print(f"\n✓ Измерение остановлено Arduino")
            
            time.sleep(0.001)
    
    def _show_db_stats(self):
        """Показывает общую статистику из БД"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                COUNT(DISTINCT session_id) as sessions,
                COUNT(*) as total_groups,
                AVG(avg_latency_us) as avg_latency,
                MIN(min_latency_us) as min_latency,
                MAX(max_latency_us) as max_latency,
                AVG(avg_jitter_us) as avg_jitter
            FROM measurements
        ''')
        
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0] > 0:
            print(f"  Сессий в БД: {row[0]}")
            print(f"  Всего групп: {row[1]}")
            print(f"  Средняя задержка: {row[2]:.2f} мкс")
            print(f"  Мин задержка: {row[3]:.2f} мкс")
            print(f"  Макс задержка: {row[4]:.2f} мкс")
            print(f"  Средний джиттер: {row[5]:.2f} мкс")

def main():
    parser = argparse.ArgumentParser(description='Демон сбора данных с Arduino')
    parser.add_argument('--db', default='arduino_data.db', help='Путь к SQLite БД')
    parser.add_argument('--port', help='COM-порт Arduino')
    parser.add_argument('--baud', type=int, default=115200, help='Скорость (по умолч. 115200)')
    
    args = parser.parse_args()
    
    collector = ArduinoCollector(
        db_path=args.db,
        port=args.port,
        baudrate=args.baud
    )
    
    if not collector.connect():
        sys.exit(1)
    
    collector.run()

if __name__ == "__main__":
    main()