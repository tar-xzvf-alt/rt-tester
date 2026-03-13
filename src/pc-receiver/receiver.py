#!/usr/bin/env python3
"""
Arduino Data Collection Daemon

This script collects measurement data from Arduino via serial connection,
stores it in SQLite database, and monitors for system falls/recoveries.
"""

import time
import argparse
import sys
import threading
from datetime import datetime

import config
import database as db
import serial_comm
from logging_utils import setup_session_logging
from arduino_monitor import FallMonitor
from config_loader import load_config

class ArduinoCollector:
    """
    Main collector class for Arduino data acquisition.
    
    Handles serial communication, data storage, and system monitoring.
    """
    
    def __init__(self, config_dict, port=None, baudrate=config.DEFAULT_BAUDRATE):
        """
        Initialize Arduino collector with configuration.
        
        Args:
            config_dict: Complete configuration dictionary from load_config()
            port: Serial port for Arduino (overrides config)
            baudrate: Serial communication speed
        """
        self.config = config_dict
        self.db_path = config_dict['db']
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False
        self.groups_received = 0
        self.groups_try_received = 0
        self.start_time = None
        self.current_session_id = None
        self.last_group_index = 0
        self.start_command_time_us = 0
        self.is_collecting = False
        
        # Auto-stop configuration
        self.auto_stop_groups = config_dict.get('auto-stop-groups')
        self.auto_stop_triggered = False
        
        
        # Logger for session logging
        self.session_logger = None
        
        # Initialize database
        db.init_database(self.db_path)
        
        # Setup fall monitor
        self.fall_monitor = FallMonitor(
            timeout_us=config_dict['timeout-us'],
            on_fall=self._on_fall_detected,
            on_recovery=self._on_recovery_detected
        )
        
        self.check_interval_us = config_dict['check-interval-us']
        
        self._print_init_info()
    
    def _print_init_info(self):
        """Print initialization information."""
        timeout_us = self.config['timeout-us']
        check_us = self.config['check-interval-us']
        timeout_sec = timeout_us / 1_000_000
        check_sec = check_us / 1_000_000
        
        print(f"✓ Database initialized: {self.db_path}")
        print(f"  Fall monitoring: timeout {timeout_us:,} µs ({timeout_sec:.1f} sec)")
        print(f"  Check interval: {check_us:,} µs ({check_sec:.1f} sec)")
        
        if self.auto_stop_groups:
            print(f"  Auto-stop: after {self.auto_stop_groups} groups")
        else:
            print(f"  Auto-stop: disabled")
        
    
    def _on_fall_detected(self, time_since_last_data_us: int) -> None:
        """Callback when fall is detected."""
        elapsed_since_start_us = (time.time_ns() // 1000) - self.start_command_time_us
        elapsed_sec = elapsed_since_start_us / 1_000_000
        
        print(f"\n⚠️ SYSTEM FALL DETECTED!")
        print(f"   Time: {datetime.now().strftime('%H:%M:%S')}")
        print(f"   Time since start: {elapsed_sec:.3f} sec ({elapsed_since_start_us:,} µs)")
        print(f"   Last group received: {self.last_group_index}")
        print(f"   No data for: {time_since_last_data_us / 1_000_000:.3f} sec ({time_since_last_data_us:,} µs)")
        
        # Save to database
        db.save_fall_event(
            self.db_path, self.current_session_id, "fall",
            self.last_group_index, f"Timeout {time_since_last_data_us} µs",
            self.start_command_time_us
        )
        
        # Log to session file
        if self.session_logger:
            self.session_logger.info(f"FALL detected, last group: {self.last_group_index}")
    
    def _on_recovery_detected(self, fall_duration_us: int) -> None:
        """Callback when recovery is detected."""
        print(f"\n✅ SYSTEM RECOVERED!")
        print(f"   Time: {datetime.now().strftime('%H:%M:%S')}")
        print(f"   Fall duration: {fall_duration_us / 1_000_000:.3f} sec ({fall_duration_us:,} µs)")
        print(f"   Last group before fall: {self.last_group_index}")
        
        # Save to database
        db.save_fall_event(
            self.db_path, self.current_session_id, "recovery",
            self.last_group_index, f"Fall duration {fall_duration_us} µs",
            self.start_command_time_us
        )
        
        # Log to session file
        if self.session_logger:
            self.session_logger.info(f"RECOVERY after {fall_duration_us / 1_000_000:.3f} sec")
    
    def connect(self) -> bool:
        """Connect to Arduino."""
        self.ser = serial_comm.connect_to_arduino(self.port, self.baudrate)
        
        # Guarantee what measeurement is stopped
        self.send_command("STOP")

        return self.ser is not None


    def send_command(self, command: str) -> None:
        """Send command to Arduino."""
        serial_comm.send_command(self.ser, command)


    def _handle_group_data(self, msg: dict) -> None:
        current_time_us = time.time_ns() // 1000
        group_index = msg['group_index']
        
        if self.is_collecting:

            # Save group data
            group_id = db.save_group_data(self.db_path, msg, current_time_us)
        
            if group_id:
                self.groups_received += 1
                self.last_group_index = group_index
                
                if self.session_logger:
                    self.session_logger.info(
                        f"Group {group_index} received, "
                    )
        else:
            self.session_logger.info(f"BAD GROUP!!!")
        

    def _check_auto_stop(self) -> None:
        """Check if auto-stop condition is met."""
        if (self.auto_stop_groups and 
            self.groups_received >= self.auto_stop_groups and 
            not self.auto_stop_triggered):
            
            self.auto_stop_triggered = True
            print(f"\n🛑 Auto-stop triggered after {self.groups_received} groups")
            
            if self.session_logger:
                self.session_logger.info(f"Auto-stop triggered after {self.groups_received} groups")
            
            self.send_command("STOP")
            self.is_collecting = False
            
            if self.session_logger:
                duration_us = (time.time_ns() // 1000) - self.start_command_time_us
                self.session_logger.info(f"Session ended. Total groups: {self.groups_received}")
                self.session_logger.info(f"Session duration: {duration_us / 1_000_000:.3f} sec")
    

    def run(self):
        """Main execution loop."""
        self.running = True
        self.start_time = time.time()
        
        self._print_welcome()
        
        # Start threads
        read_thread = threading.Thread(target=self._read_loop)
        read_thread.daemon = True
        read_thread.start()
        
        monitor_thread = threading.Thread(target=self._monitor_loop)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Command loop
        try:
            while self.running:
                cmd = input("\n> ").strip().lower()
                self._handle_command(cmd)
        except KeyboardInterrupt:
            print("\n\nUser interrupt")
        finally:
            self.running = False
            if self.ser:
                self.ser.close()
            print("✓ Connection closed")
            print(f"✓ Data saved to {self.db_path}")
    
    def _print_welcome(self) -> None:
        """Print welcome message."""
        timeout_sec = self.fall_monitor.timeout_us / 1_000_000
        check_sec = self.check_interval_us / 1_000_000
        
        print("\n" + "="*80)
        print("ARDUINO DATA COLLECTION DAEMON WITH FALL MONITORING")
        print("="*80)
        print(f"Database: {self.db_path}")
        print("Mode: collecting 25 worst latencies per group")
        print(f"Monitoring: timeout {self.fall_monitor.timeout_us:,} µs ({timeout_sec:.1f} sec)")
        print(f"            check every {self.check_interval_us:,} µs ({check_sec:.1f} sec)")
        if self.auto_stop_groups:
            print(f"Auto-stop: after {self.auto_stop_groups} groups")
        print("Commands: start, stop, status, events, exit")
        print("="*80)
    
    def _handle_command(self, cmd: str) -> None:
        """Handle user commands."""
        commands = {
            "start": self._cmd_start,
            "stop": self._cmd_stop,
            "status": self._cmd_status,
            "events": self._cmd_events,
            "exit": self._cmd_exit,
            "help": self._cmd_help
        }
        
        if cmd in commands:
            commands[cmd]()
        else:
            print(f"Unknown command: {cmd}")
    
    def _cmd_start(self) -> None:
        """Handle start command."""
        if self.auto_stop_groups:
            start_cmd = f"START {self.auto_stop_groups}"
        else:
            start_cmd = "START"
        
        self.send_command(start_cmd)
        self.start_command_time_us = time.time_ns() // 1000
        self.is_collecting = True
        self.groups_received = 0
        self.groups_try_received = 0
        self.last_group_index = 0
        self.auto_stop_triggered = False
        self.fall_monitor.reset()
        print(f"✓ Measurement started, fall monitoring active" + 
            (f" (will stop after {self.auto_stop_groups} groups)" if self.auto_stop_groups else ""))
        
    def _cmd_stop(self) -> None:
        """Handle stop command."""
        self.send_command("STOP")
        self.is_collecting = False
        print("✓ Measurement stopped")
        if self.session_logger:
            self.session_logger.info("Measurement stopped by user")
    
    def _cmd_status(self) -> None:
        """Handle status command."""
        self._show_status()
    
    def _cmd_events(self) -> None:
        """Handle events command."""
        self._show_recent_events()
    
    def _cmd_exit(self) -> None:
        """Handle exit command."""
        print("Shutting down...")
        self.running = False
    
    def _cmd_help(self) -> None:
        """Handle help command."""
        print("\nAvailable commands:")
        print("  start  - start measurement")
        print("  stop   - stop measurement")
        print("  status - show statistics")
        print("  events - show recent events")
        print("  exit   - exit program")
    
    def _monitor_loop(self) -> None:
        while self.running:
            if self.is_collecting:
                current_time_us = time.time_ns() // 1000
                self.fall_monitor.check(current_time_us)
                self._check_auto_stop()
            time.sleep(self.check_interval_us / 1_000_000)
    
    def _read_loop(self) -> None:
        """Data reading thread."""
        while self.running:
            msg = serial_comm.read_json_message(self.ser)
            if msg:
                # Update last data time
                self.fall_monitor.update_last_data_time()
                
                if "group_index" in msg and "worst_latencies_us" in msg:
                    # First group of session?
                    if self.current_session_id is None:
                        self.current_session_id = msg.get('session_id')
                        self.session_logger = setup_session_logging(self.current_session_id)
                        print(f"\n✓ New session ID: {self.current_session_id}")
                        if self.session_logger:
                            self.session_logger.info(f"=== Session {self.current_session_id} started ===")
                            self.session_logger.info(f"Auto-stop groups: {self.auto_stop_groups}")
                    
                    self.groups_try_received+=1

                    self._handle_group_data(msg)
                
                elif "status" in msg:
                    self._handle_status_message(msg)
            
            time.sleep(config.READ_SLEEP)
    
    def _handle_status_message(self, msg: dict) -> None:
        """Handle status messages from Arduino."""
        status = msg.get('status')
        if status == 'started':
            self.current_session_id = msg.get('session_id')
            self.session_logger = setup_session_logging(self.current_session_id)
            print(f"\n✓ New session ID: {self.current_session_id}")
            
        
        elif status == 'stopped':
            print(f"\n✓ Measurement stopped by Arduino")
            self.is_collecting = False
            
            if self.session_logger:
                duration_us = (time.time_ns() // 1000) - self.start_command_time_us
                self.session_logger.info(f"Session ended. Total groups: {self.groups_received}")
                self.session_logger.info(f"Session duration: {duration_us / 1_000_000:.3f} sec")
        
    def _show_status(self) -> None:
        """Show extended status with fall information."""
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        
        current_time_us = time.time_ns() // 1000
        
        print(f"\n📊 STATISTICS:")
        print(f"  Uptime: {hours:02d}:{minutes:02d}:{seconds:02d}")
        print(f"  Groups received: {self.groups_received}")
        print(f"  Total latencies: {self.groups_received * 25:,}")
        print(f"  Last group: {self.last_group_index}")
        
        # Collection state
        if self.is_collecting:
            print(f"  State: COLLECTING")
            if self.start_command_time_us:
                collecting_time_us = current_time_us - self.start_command_time_us
                print(f"  Collection time: {collecting_time_us / 1_000_000:.3f} sec ({collecting_time_us:,} µs)")
        else:
            print(f"  State: IDLE")
        
        # Auto-stop info
        if self.auto_stop_groups:
            progress = (self.groups_received / self.auto_stop_groups) * 100
            print(f"  Auto-stop: {self.groups_received}/{self.auto_stop_groups} groups ({progress:.1f}%)")
        
        # Fall information
        if self.fall_monitor.last_data_time_us > 0 and self.is_collecting:
            time_since_last_us = current_time_us - self.fall_monitor.last_data_time_us
            status = "⚠️ FALL" if time_since_last_us > self.fall_monitor.timeout_us else "✅ OK"
            print(f"  Last data: {time_since_last_us / 1_000_000:.3f} sec ago ({status})")
            print(f"  Since last data: {time_since_last_us:,} µs")
        
        if self.fall_monitor.is_fallen:
            fall_duration_us = current_time_us - self.fall_monitor.fall_start_time_us
            print(f"  ⚠️ CURRENT FALL: {fall_duration_us / 1_000_000:.3f} sec ({fall_duration_us:,} µs)")
        
        if self.groups_received > 0:
            rate = self.groups_received / elapsed
            print(f"  Average rate: {rate:.2f} groups/sec")
            self._show_db_stats()
    
    def _show_recent_events(self, limit: int = 10) -> None:
        """Show recent fall/recovery events."""
        events = db.get_recent_events(self.db_path, self.current_session_id, limit)
        
        if not events:
            print("\n📋 No events in current session")
            return
        
        print(f"\n📋 RECENT EVENTS (session {self.current_session_id}):")
        print("="*100)
        print(f"{'Type':<12} {'Time':<20} {'Time(µs)':<18} {'Since start(µs)':<18} {'Group':<8} {'Details'}")
        print("-"*100)
        
        for event in events:
            event_type = "⚠️ FALL" if event[0] == "fall" else "✅ RECOVERY"
            time_str = event[1][11:19] if event[1] else "N/A"
            print(f"{event_type:<12} {time_str:<20} {event[2]:<18,} {event[3]:<18,} {event[4]:<8} {event[5]}")
        
        print("="*100)
    
    def _show_db_stats(self) -> None:
        """Show database statistics."""
        row, events_row = db.get_db_stats(self.db_path, self.current_session_id)
        
        if row and row[0] > 0:
            print(f"  Sessions in DB: {row[0]}")
            print(f"  Total groups: {row[1]}")
            print(f"  Total latencies: {row[2]:,}")
            print(f"  Avg latency (top-25 worst): {row[4]:.2f} µs")
            print(f"  Min latency (from worst 25): {row[5]:.2f} µs")
            print(f"  Max latency: {row[6]:.2f} µs")
            print(f"  Avg jitter: {row[3]:.2f} µs")
            
            if events_row and events_row[0] > 0:
                print(f"  Falls in session: {events_row[0]}")
                print(f"  Recoveries: {events_row[1]}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Arduino Data Collection Daemon'
    )
    parser.add_argument('--params', help='Path to configuration file')
    parser.add_argument('--port', help='Arduino COM port (overrides config)')
    parser.add_argument('--baud', type=int, default=config.DEFAULT_BAUDRATE, 
                       help=f'Baud rate (default: {config.DEFAULT_BAUDRATE})')
    
    args = parser.parse_args()
    
    config_dict = load_config(args.params)
    
    collector = ArduinoCollector(
        config_dict=config_dict,
        port=args.port,
        baudrate=args.baud
    )
    
    if not collector.connect():
        sys.exit(1)
    
    collector.run()


if __name__ == "__main__":
    main()