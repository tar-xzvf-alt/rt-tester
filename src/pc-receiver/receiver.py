#!/usr/bin/env python3
"""
Arduino Data Collection Daemon
"""

import time
import argparse
import sys
import threading
from datetime import datetime
import random
import config
import database as db
import serial_comm
from logging_utils import setup_session_logging
from arduino_monitor import FallMonitor
from config_loader import load_config
import json
from metrics_server import MetricsServer
from prometheus_client import get_node_exporter_metrics


class ArduinoCollector:
    """
    Main collector class for Arduino data acquisition.
    """
    
    def __init__(self, config_dict, port=None, baudrate=config.DEFAULT_BAUDRATE):
        """
        Initialize Arduino collector with configuration.
        """
        self.config = config_dict
        self.db_path = config_dict['db']
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False
        self.groups_received = 0
        self.start_time = None
        self.current_session_id = None
        self.last_group_index = 0
        self.start_command_time_us = 0
        self.is_collecting = False

        # Measurement parameters
        self.worst_count = config_dict.get('worst-count', config.DEFAULT_WORST_COUNT)
        self.measurement_interval_us = config_dict.get('measurement-interval-us', 
                                                       config.DEFAULT_MEASUREMENT_INTERVAL_US)
        
        # Target device information
        self.target_board = config_dict.get('target-board', config.DEFAULT_TARGET_BOARD)
        self.target_kernel = config_dict.get('target-kernel', config.DEFAULT_TARGET_KERNEL)
        self.target_stress = config_dict.get('target-stress', config.DEFAULT_TARGET_STRESS)


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
        
        # Initialize metrics server for Prometheus
        self.metrics_server = MetricsServer(port=9101)
        self.metrics_server.start()
        
        self._print_init_info()
    
    
    def _print_init_info(self):
        """Print initialization information."""
        timeout_us = self.config['timeout-us']
        check_us = self.config['check-interval-us']
        timeout_sec = timeout_us / 1_000_000
        check_sec = check_us / 1_000_000
        
        stress_status = "ON" if self.target_stress == 'on' else "OFF"
        
        print(f"Database initialized: {self.db_path}")
        print(f"  Fall monitoring: timeout {timeout_us:,} µs ({timeout_sec:.1f} sec)")
        print(f"  Check interval: {check_us:,} µs ({check_sec:.1f} sec)")
        print(f"  Target device: {self.target_board} (kernel: {self.target_kernel}) - Stress: {stress_status}")
        print(f"  Measurement parameters:")
        print(f"    Worst count: {self.worst_count}")
        print(f"    Measurement interval: {self.measurement_interval_us} µs")
        
        if self.auto_stop_groups:
            print(f"  Auto-stop: after {self.auto_stop_groups} groups")
        else:
            print(f"  Auto-stop: disabled")
    

    def _on_fall_detected(self, time_since_last_data_us: int) -> None:
        """Callback when fall is detected."""
        elapsed_since_start_us = (time.time_ns() // 1000) - self.start_command_time_us
        elapsed_sec = elapsed_since_start_us / 1_000_000
        
        print(f"\nSYSTEM FALL DETECTED!")
        print(f"   Time: {datetime.now().strftime('%H:%M:%S')}")
        print(f"   Time since start: {elapsed_sec:.3f} sec")
        print(f"   Last group received: {self.last_group_index}")
        print(f"   No data for: {time_since_last_data_us / 1_000_000:.3f} sec")
        
        # Save to database using unified event system
        db.save_event(
            self.db_path,
            self.current_session_id,
            "fall",
            self.last_group_index,
            f"Timeout {time_since_last_data_us} µs",
            self.start_command_time_us
        )
        
        if self.session_logger:
            self.session_logger.info(f"FALL detected, last group: {self.last_group_index}")
        
    def _on_recovery_detected(self, fall_duration_us: int) -> None:
        """Callback when recovery is detected."""
        print(f"\nSYSTEM RECOVERED!")
        print(f"   Time: {datetime.now().strftime('%H:%M:%S')}")
        print(f"   Fall duration: {fall_duration_us / 1_000_000:.3f} sec")
        print(f"   Last group before fall: {self.last_group_index}")
        
        # Save to database using unified event system
        db.save_event(
            self.db_path,
            self.current_session_id,
            "recovery",
            self.last_group_index,
            f"Fall duration {fall_duration_us} µs",
            self.start_command_time_us
        )
        
        if self.session_logger:
            self.session_logger.info(f"RECOVERY after {fall_duration_us / 1_000_000:.3f} sec")
    
    def connect(self) -> bool:
        """Connect to Arduino."""
        self.ser = serial_comm.connect_to_arduino(self.port, self.baudrate)
        
        # Guarantee that measurement is stopped
        self.send_command("STOP")

        return self.ser is not None


    def send_command(self, command: str) -> None:
        """Send command to Arduino."""
        serial_comm.send_command(self.ser, command)


    def _handle_group_data(self, msg: dict) -> None:
        current_time_us = time.time_ns() // 1000
        group_index = msg['group_index']
        msg_session_id = msg.get('session_id')
        
        # Check session_id
        if msg_session_id != self.current_session_id:
            print(f"Warning: Session ID mismatch in group {group_index}: "
                  f"expected {self.current_session_id}, got {msg_session_id}")
            self.current_session_id = msg_session_id
            self.session_logger = setup_session_logging(self.current_session_id)
        
        if self.is_collecting:
            # Add target info to the message for Prometheus metrics
            msg['board'] = self.target_board
            msg['kernel'] = self.target_kernel
            msg['stress'] = self.target_stress
            
            # Send to metrics server for Prometheus
            self.metrics_server.add_group(msg)
            
            # Get CPU/memory from node_exporter via Prometheus
            node_metrics = get_node_exporter_metrics()
            if node_metrics['cpu_percent'] is not None:
                msg['soc_cpu_percent'] = node_metrics['cpu_percent']
                msg['soc_memory_percent'] = node_metrics['memory_percent'] if node_metrics['memory_percent'] else 0
            
            with open('/tmp/metrics_all_groups.log', 'a') as f:
                f.write(json.dumps(msg) + '\n')
            
            # Pass target info to database
            group_id = db.save_group_data(
                self.db_path, 
                msg, 
                current_time_us,
                self.target_board,
                self.target_kernel,
                self.target_stress
            )
            
            if group_id:
                self.groups_received += 1
                self.last_group_index = group_index
                
                if self.session_logger:
                    self.session_logger.info(f"Group {group_index} received")
        else:
            if self.session_logger:
                self.session_logger.info(f"Received group {group_index} while not collecting")


    def _check_auto_stop(self) -> None:
        """Check if auto-stop condition is met."""
        if (self.auto_stop_groups and 
            self.groups_received >= self.auto_stop_groups and 
            not self.auto_stop_triggered):
            
            self.auto_stop_triggered = True
            print(f"\nAuto-stop triggered after {self.groups_received} groups")
            
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
            print("Connection closed")
            print(f"Data saved to {self.db_path}")
    
    def _print_welcome(self) -> None:
        """Print welcome message."""
        timeout_sec = self.fall_monitor.timeout_us / 1_000_000
        check_sec = self.check_interval_us / 1_000_000
        
        print("\n" + "="*80)
        print("ARDUINO DATA COLLECTION DAEMON WITH FALL MONITORING")
        print("="*80)
        print(f"Database: {self.db_path}")
        print("Mode: collecting N worst latencies per group")
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
        session_id = random.randint(100000, 999999)
        
        # Form command for Arduino
        params = {
            "session_id": session_id,
            "groups": self.auto_stop_groups if self.auto_stop_groups else 0,
            "worst_count": self.worst_count,
            "interval_us": self.measurement_interval_us
        }
        
        cmd = f"START {json.dumps(params)}"
        self.send_command(cmd)
        
        # Save session information
        self.current_session_id = session_id
        self.start_command_time_us = time.time_ns() // 1000
        self.is_collecting = True
        self.groups_received = 0
        self.last_group_index = -1
        self.auto_stop_triggered = False
        self.fall_monitor.reset()
        
        # Update metrics server with new session
        self.metrics_server.update_session(str(session_id))
        
        # Save session start event with target info
        db.save_session_start(
            self.db_path, 
            session_id, 
            self.auto_stop_groups or 0,
            self.worst_count,
            self.measurement_interval_us,
            self.target_board,
            self.target_kernel,
            self.target_stress
        )
        
        print(f"Measurement started with session ID: {session_id}")
        stress_status = "WITH STRESS" if self.target_stress == 'on' else "NO STRESS"
        print(f"  Target: {self.target_board} (kernel: {self.target_kernel}) - {stress_status}")
        print(f"  Parameters: worst_count={self.worst_count}, interval={self.measurement_interval_us} µs")
        if self.auto_stop_groups:
            print(f"  Auto-stop: after {self.auto_stop_groups} groups")
        
        # Initialize session logger
        self.session_logger = setup_session_logging(session_id)
        if self.session_logger:
            self.session_logger.info(f"=== Session {session_id} started ===")
            self.session_logger.info(f"Target board: {self.target_board}")
            self.session_logger.info(f"Target kernel: {self.target_kernel}")
            self.session_logger.info(f"Target stress: {self.target_stress}")
            self.session_logger.info(f"Auto-stop groups: {self.auto_stop_groups}")
            self.session_logger.info(f"Worst count: {self.worst_count}")
            self.session_logger.info(f"Measurement interval: {self.measurement_interval_us} µs")


    def _cmd_stop(self) -> None:
        """Handle stop command with log processing."""
        self.send_command("STOP")
        self.is_collecting = False
        
        print("Measurement stopped")
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
                if self.fall_monitor.last_data_time_us > 0:
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
                        print(f"\nNew session ID: {self.current_session_id}")
                        if self.session_logger:
                            self.session_logger.info(f"=== Session {self.current_session_id} started ===")
                            self.session_logger.info(f"Auto-stop groups: {self.auto_stop_groups}")
                    
                    self._handle_group_data(msg)
                
                elif "status" in msg:
                    self._handle_status_message(msg)
            
            time.sleep(config.READ_SLEEP)
    
    def _handle_status_message(self, msg: dict) -> None:
        """Handle status messages from Arduino."""
        status = msg.get('status')
        
        if status == 'stopped':
            print(f"\nMeasurement stopped by Arduino")
            self.is_collecting = False
            
            duration_us = (time.time_ns() // 1000) - self.start_command_time_us
            
            # Save session stop event
            db.save_session_stop(
                self.db_path,
                self.current_session_id,
                self.groups_received,
                duration_us,
                "arduino"
            )
                        
            if self.session_logger:
                self.session_logger.info(f"Session ended. Total groups: {self.groups_received}")
                self.session_logger.info(f"Session duration: {duration_us / 1_000_000:.3f} sec")
        
        elif status == 'auto_stopped':
            groups = msg.get('groups_collected', 0)
            print(f"\nArduino auto-stopped after {groups} groups")
            self.is_collecting = False
            
            duration_us = (time.time_ns() // 1000) - self.start_command_time_us
            
            # Save auto-stop event
            db.save_session_stop(
                self.db_path,
                self.current_session_id,
                groups,
                duration_us,
                "auto"
            )
            
            if self.session_logger:
                self.session_logger.info(f"Session auto-stopped. Total groups: {groups}")
                self.session_logger.info(f"Session duration: {duration_us / 1_000_000:.3f} sec")
        
    def _show_status(self) -> None:
        """Show extended status with fall information."""
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        
        current_time_us = time.time_ns() // 1000
        
        print(f"\nSTATISTICS:")
        print(f"  Uptime: {hours:02d}:{minutes:02d}:{seconds:02d}")
        print(f"  Groups received: {self.groups_received}")
        print(f"  Total latencies: {self.groups_received * self.worst_count}")
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
            status = "FALL" if time_since_last_us > self.fall_monitor.timeout_us else "OK"
            print(f"  Last data: {time_since_last_us / 1_000_000:.3f} sec ago ({status})")
            print(f"  Since last data: {time_since_last_us:,} µs")
        
        if self.fall_monitor.is_fallen:
            fall_duration_us = current_time_us - self.fall_monitor.fall_start_time_us
            print(f"  CURRENT FALL: {fall_duration_us / 1_000_000:.3f} sec ({fall_duration_us:,} µs)")
        
        if self.groups_received > 0:
            rate = self.groups_received / elapsed
            print(f"  Average rate: {rate:.2f} groups/sec")
            self._show_db_stats()

    def _show_recent_events(self, limit: int = 10) -> None:
        """Show recent fall/recovery events."""
        events = db.get_recent_events(self.db_path, self.current_session_id, limit)
        
        if not events:
            print("\nNo events in current session")
            return
        
        print(f"\nRECENT EVENTS (session {self.current_session_id}):")
        print("="*100)
        print(f"{'Type':<12} {'Time':<20} {'Time(µs)':<18} {'Since start(µs)':<18} {'Group':<8} {'Details'}")
        print("-"*100)
        
        for event in events:
            event_type = "FALL" if event[0] == "fall" else "RECOVERY"
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
            print(f"  Avg latency (top-n worst): {row[4]:.2f} µs")
            print(f"  Min latency (from worst n): {row[5]:.2f} µs")
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