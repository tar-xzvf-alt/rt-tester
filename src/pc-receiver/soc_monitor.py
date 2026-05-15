#!/usr/bin/env python3
"""
SoC (System on Chip) Manager Module

Handles all communication with the target device (Radxa/Lichee/etc.):
- SSH connection management with auto-reconnect
- Reading metrics from log file
- Sending signals to reset counters
- Parsing log entries
"""

import time
import re
import paramiko
from datetime import datetime
import os
from typing import Optional, List, Dict, Tuple


class SSHConnection:
    """
    SSH connection manager with automatic reconnection.
    """
    
    def __init__(self, host: str, port: int, username: str, password: str, logger=None):
        """
        Initialize SSH connection manager.
        
        Args:
            host: SSH server hostname/IP
            port: SSH port (default 22)
            username: SSH username
            password: SSH password
            logger: Logger instance for logging (optional)
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.logger = logger
        
        self.client = None
        self.transport = None
        self.is_connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 2  # seconds
        
        # Statistics
        self.connection_stats = {
            'connected_at': None,
            'last_check': None,
            'reconnections': 0,
            'failed_attempts': 0
        }
    
    def connect(self) -> bool:
        """
        Establish SSH connection.
        
        Returns:
            bool: True if connected successfully
        """
        try:
            if self.client:
                self.disconnect()
            
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=str(self.password),
                timeout=5,
                allow_agent=True,
                look_for_keys=True
            )
            
            self.transport = self.client.get_transport()
            self.is_connected = True
            self.reconnect_attempts = 0
            self.connection_stats['connected_at'] = time.time()
            self.connection_stats['reconnections'] += 1
            
            self._log_info(f"SSH connected to {self.host}")
            return True
            
        except Exception as e:
            self.is_connected = False
            self.connection_stats['failed_attempts'] += 1
            self._log_error(f"SSH connection failed: {e}")
            return False
    
    def disconnect(self) -> None:
        """Close SSH connection."""
        if self.client:
            try:
                self.client.close()
            except:
                pass
            self.client = None
            self.transport = None
        
        self.is_connected = False
        self._log_info("SSH disconnected")
    
    def is_active(self) -> bool:
        """
        Check if connection is active.
        
        Returns:
            bool: True if connection is active
        """
        if not self.client or not self.transport:
            return False
        
        try:
            # Check if transport is active
            if not self.transport.is_active():
                return False
            
            # Try to execute a simple command to verify
            stdin, stdout, stderr = self.client.exec_command("echo ok", timeout=2)
            result = stdout.read().decode().strip()
            
            return result == "ok"
            
        except Exception as e:
            self._log_debug(f"SSH active check failed: {e}")
            return False
    
    def ensure_connection(self) -> bool:
        """
        Ensure connection is active, reconnect if needed.
        
        Returns:
            bool: True if connection is active
        """
        if self.is_active():
            self.connection_stats['last_check'] = time.time()
            self.reconnect_attempts = 0
            return True
        
        # Connection lost, try to reconnect
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            self._log_warning(f"Max reconnect attempts ({self.max_reconnect_attempts}) reached")
            return False
        
        self.reconnect_attempts += 1
        self._log_info(f"SSH connection lost, reconnecting (attempt {self.reconnect_attempts})...")
        
        if self.connect():
            return True
        
        # Wait before next attempt
        time.sleep(self.reconnect_delay)
        return False
    
    def exec_command(self, command: str, timeout: int = 10) -> Tuple[Optional[any], Optional[any]]:
        """
        Execute command on remote host with automatic reconnection.
        
        Args:
            command: Command to execute
            timeout: Command timeout in seconds
        
        Returns:
            tuple: (stdout, stderr) or (None, None) on failure
        """
        if not self.ensure_connection():
            return None, None
        
        try:
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            return stdout, stderr
        except Exception as e:
            self._log_error(f"SSH command execution failed: {e}")
            # Mark as disconnected to force reconnect next time
            self.is_connected = False
            return None, None
    
    def read_file(self, path: str) -> Optional[List[str]]:
        """
        Read file content from remote host.
        
        Args:
            path: Path to file on remote host
        
        Returns:
            List of lines or None on failure
        """
        cmd = f"cat {path} 2>/dev/null || echo ''"
        stdout, stderr = self.exec_command(cmd, timeout=30)
        
        if stdout:
            output = stdout.read().decode().strip()
            if output:
                return output.split('\n')
        
        return None
    
    def write_file(self, path: str, content: str) -> bool:
        """
        Write content to file on remote host.
        
        Args:
            path: Path to file on remote host
            content: Content to write
        
        Returns:
            bool: True if successful
        """
        # Escape content for shell
        escaped_content = content.replace("'", "'\\''")
        cmd = f"echo '{escaped_content}' > {path}"
        stdout, stderr = self.exec_command(cmd)
        
        if stderr:
            error = stderr.read().decode().strip()
            if error:
                self._log_error(f"Write failed: {error}")
                return False
        
        return True
    
    def clear_file(self, path: str) -> bool:
        """
        Clear file content on remote host.
        
        Args:
            path: Path to file on remote host
        
        Returns:
            bool: True if successful
        """
        return self.write_file(path, "")
    
    def send_signal(self, process_name: str, signal: int) -> bool:
        """
        Send signal to process on remote host.
        
        Args:
            process_name: Name of the process (e.g., 'radxa-monitor')
            signal: Signal number (e.g., 10 for SIGUSR1)
        
        Returns:
            bool: True if signal was sent successfully
        """
        # Send signal via pkill
        cmd = f"pkill -{signal} {process_name} 2>/dev/null || true"
        stdout, stderr = self.exec_command(cmd)
        
        # Check if process was found
        cmd = f"pgrep {process_name} || echo 'not running'"
        stdout, stderr = self.exec_command(cmd)
        
        if stdout:
            result = stdout.read().decode().strip()
            if result and result != 'not running':
                self._log_info(f"Signal {signal} sent to {process_name} (PID: {result})")
                return True
            else:
                self._log_warning(f"{process_name} not running on target device")
                return False
        
        return False
    
    def get_stats(self) -> Dict:
        """
        Get connection statistics.
        
        Returns:
            dict: Connection statistics
        """
        stats = self.connection_stats.copy()
        stats['is_connected'] = self.is_connected
        stats['reconnect_attempts_remaining'] = self.max_reconnect_attempts - self.reconnect_attempts
        stats['host'] = self.host
        stats['port'] = self.port
        stats['username'] = self.username
        
        if self.is_connected and self.connection_stats['connected_at']:
            stats['uptime_seconds'] = time.time() - self.connection_stats['connected_at']
        else:
            stats['uptime_seconds'] = 0
        
        return stats
    
    def _log_info(self, message: str) -> None:
        """Log info message."""
        if self.logger:
            self.logger.info(message)
        else:
            print(message)
    
    def _log_error(self, message: str) -> None:
        """Log error message."""
        if self.logger:
            self.logger.error(message)
        else:
            print(f"ERROR: {message}")
    
    def _log_warning(self, message: str) -> None:
        """Log warning message."""
        if self.logger:
            self.logger.warning(message)
        else:
            print(f"WARNING: {message}")
    
    def _log_debug(self, message: str) -> None:
        """Log debug message."""
        if self.logger:
            self.logger.debug(message)


class SoCMetricsReader:
    """
    Reads and parses SoC metrics from log file.
    """
    
    # Log format patterns
    PATTERNS = {
        'group_index': r'GROUP=(\d+)',
        'cpu_max': r'CPU_MAX=([\d.]+)',
        'mem_max': r'MEM_MAX=([\d.]+)',
        'cpu_avg': r'CPU_AVG=([\d.]+)',
        'mem_avg': r'MEM_AVG=([\d.]+)',
        'samples': r'SAMPLES=(\d+)',
        'duration_ms': r'DURATION_MS=([\d.]+)'
    }
    
    def __init__(self, ssh_conn: SSHConnection, log_path: str = "/var/log/soc_metrics.log"):
        """
        Initialize SoC metrics reader.
        
        Args:
            ssh_conn: SSH connection manager
            log_path: Path to log file on remote host
        """
        self.ssh_conn = ssh_conn
        self.log_path = log_path
    
    def clear_log_and_reset_counter(self, process_name: str = "radxa-monitor") -> bool:
        """
        Clear log file and reset group counter on target device.
        
        Args:
            process_name: Name of the monitoring process
        
        Returns:
            bool: True if successful
        """
        if not self.ssh_conn:
            return False
        
        try:
            # 1. Clear log file
            print("  Cleaning log file...")
            if not self.ssh_conn.clear_file(self.log_path):
                print("  Warning: Failed to clear log file")
            
            # 2. Send USR1 signal (10) to reset counter
            print("  Resetting group counter...")
            self.ssh_conn.send_signal(process_name, 10)  # 10 = SIGUSR1
            
            # 3. Small pause for signal processing
            time.sleep(0.1)
            
            # 4. Check result - read first line of log (should be comment)
            first_line = self._get_first_log_line()
            
            if first_line is None or first_line.startswith('#') or first_line == 'empty':
                print(f"  Log cleared and counter reset confirmed")
                return True
            else:
                print(f"  Log may not be empty: {first_line[:50]}")
                return False
            
        except Exception as e:
            print(f"Failed to clear log and reset counter: {e}")
            return False
    
    def read_all_metrics(self, session_id: int) -> List[Dict]:
        """
        Read and parse all metrics from log file.
        
        Args:
            session_id: Current session ID to associate with metrics
        
        Returns:
            List of parsed metric dictionaries
        """
        if not self.ssh_conn:
            print("No SSH connection, cannot read log")
            return []
        
        lines = self.ssh_conn.read_file(self.log_path)
        
        if not lines:
            print("No log entries found")
            return []
        
        # Filter out comments and empty lines
        data_lines = [line for line in lines if line and not line.startswith('#')]
        print(f"Read {len(data_lines)} data lines from log (total {len(lines)} lines)")
        
        metrics_list = []
        errors = 0
        
        for line in data_lines:
            metrics = self._parse_line(line, session_id)
            if metrics:
                metrics_list.append(metrics)
            else:
                errors += 1
                print(f"  Failed to parse line: {line[:50]}...")
        
        if errors:
            print(f"  {errors} lines failed to parse")
        
        return metrics_list
    
    def _parse_line(self, line: str, session_id: int) -> Optional[Dict]:
        """
        Parse a single log line.
        
        Format: GROUP=42 CPU_MAX=15.32 MEM_MAX=42.15 CPU_AVG=8.45 MEM_AVG=38.23 SAMPLES=1500 DURATION_MS=234.56
        
        Args:
            line: Log line to parse
            session_id: Current session ID
        
        Returns:
            Parsed metrics dictionary or None if parsing failed
        """
        metrics = {
            'session_id': session_id,
            'group_index': None,
            'cpu_max': None,
            'mem_max': None,
            'cpu_avg': None,
            'mem_avg': None,
            'samples': None,
            'duration_ms': None
        }
        
        for key, pattern in self.PATTERNS.items():
            match = re.search(pattern, line)
            if match:
                if key in ['group_index', 'samples']:
                    metrics[key] = int(match.group(1))
                else:
                    metrics[key] = float(match.group(1))
        
        # Validate required fields
        if metrics['group_index'] is None:
            return None
        
        return metrics
    
    def _get_first_log_line(self) -> Optional[str]:
        """Get first line of log file."""
        if not self.ssh_conn:
            return None
        
        cmd = f"head -1 {self.log_path} 2>/dev/null || echo 'empty'"
        stdout, stderr = self.ssh_conn.exec_command(cmd)
        
        if stdout:
            return stdout.read().decode().strip()
        
        return None


class SoCMonitor:
    """
    Main manager class for SoC operations.
    Combines SSH connection management and metrics reading.
    """
    
    def __init__(self, config: dict, logger=None):
        """
        Initialize SoC manager.
        
        Args:
            config: SoC configuration dictionary with host, port, username, password
            logger: Logger instance for logging
        """
        self.config = config
        self.logger = logger
        self.enabled = config.get('enabled', False)
        
        self.ssh_conn = None
        self.metrics_reader = None
        
        if self.enabled:
            self.ssh_conn = SSHConnection(
                host=config['host'],
                port=config.get('port', 22),
                username=config['username'],
                password=config['password'],
                logger=logger
            )
            self.metrics_reader = SoCMetricsReader(self.ssh_conn)
    
    def connect(self) -> bool:
        """Establish SSH connection."""
        if not self.enabled:
            return False
        return self.ssh_conn.connect()
    
    def disconnect(self) -> None:
        """Close SSH connection."""
        if self.ssh_conn:
            self.ssh_conn.disconnect()
    
    def is_connected(self) -> bool:
        """Check if SSH connection is active."""
        if not self.ssh_conn:
            return False
        return self.ssh_conn.is_connected and self.ssh_conn.is_active()
    
    def prepare_for_session(self, process_name: str = "radxa-monitor") -> bool:
        """
        Prepare target device for new session: clear log and reset counter.
        
        Args:
            process_name: Name of the monitoring process
        
        Returns:
            bool: True if successful
        """
        if not self.enabled or not self.ssh_conn:
            print("  SoC monitoring disabled or no SSH connection")
            return False
        
        print("  Preparing target device for new session...")
        return self.metrics_reader.clear_log_and_reset_counter(process_name)
    
    def read_session_metrics(self, session_id: int) -> List[Dict]:
        """
        Read all metrics for a session from the log file.
        
        Args:
            session_id: Current session ID
        
        Returns:
            List of parsed metric dictionaries
        """
        if not self.enabled or not self.ssh_conn:
            return []
        
        print("\nReading metrics log from target device...")
        return self.metrics_reader.read_all_metrics(session_id)
    
    def get_connection_stats(self) -> Dict:
        """
        Get SSH connection statistics.
        
        Returns:
            dict: Connection statistics
        """
        if not self.ssh_conn:
            return {'enabled': False, 'connected': False}
        
        stats = self.ssh_conn.get_stats()
        stats['enabled'] = self.enabled
        return stats
    
    def save_metrics_to_local(self, metrics_list: List[Dict], session_id: int) -> Optional[str]:
        """
        Save metrics to local file for backup.
        
        Args:
            metrics_list: List of metrics dictionaries
            session_id: Session ID
        
        Returns:
            Path to saved file or None if failed
        """
        if not metrics_list:
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        local_log = f"logs/session_{session_id}_{timestamp}.log"
        os.makedirs("logs", exist_ok=True)
        
        with open(local_log, 'w') as f:
            for metrics in metrics_list:
                # Reconstruct log line format
                line = (f"GROUP={metrics['group_index']} "
                        f"CPU_MAX={metrics['cpu_max']:.2f} "
                        f"MEM_MAX={metrics['mem_max']:.2f} "
                        f"CPU_AVG={metrics['cpu_avg']:.2f} "
                        f"MEM_AVG={metrics['mem_avg']:.2f} "
                        f"SAMPLES={metrics['samples']} "
                        f"DURATION_MS={metrics['duration_ms']:.2f}\n")
                f.write(line)
        
        print(f"  Local copy saved to {local_log}")
        return local_log