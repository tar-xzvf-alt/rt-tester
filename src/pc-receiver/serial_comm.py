"""
Serial communication utilities for Arduino collector.
"""

import serial
import serial.tools.list_ports
import json
import time
from typing import Optional, Any


def auto_detect_port() -> Optional[str]:
    """
    Auto-detect Arduino serial port.
    
    Returns:
        Port name if found, None otherwise
    """
    ports = list(serial.tools.list_ports.comports())
    for port in ports:
        if 'Arduino' in port.description or 'ACM' in port.description:
            return port.device
    
    print("Available ports:")
    for port in ports:
        print(f"  {port.device}: {port.description}")
    return None


def connect_to_arduino(port: Optional[str], baudrate: int) -> Optional[serial.Serial]:
    """
    Connect to Arduino.
    
    Args:
        port: Serial port (auto-detect if None)
        baudrate: Communication speed
    
    Returns:
        Serial object if connected, None otherwise
    """
    if not port:
        port = auto_detect_port()
        if not port:
            return None
    
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)  # Wait for Arduino reset
        
        # Clear input buffer
        ser.reset_input_buffer()
        
        print(f"✓ Connected to {port}")
        return ser
    except Exception as e:
        print(f"✗ Connection error: {e}")
        return None


def read_json_message(ser: Optional[serial.Serial]) -> Optional[Any]:
    """
    Read and parse JSON message from Arduino.
    
    Args:
        ser: Serial object
    
    Returns:
        Parsed JSON object if successful, None otherwise
    """
    if ser and ser.in_waiting > 0:
        try:
            line = ser.readline().decode('utf-8').strip()
            if line:
                return json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return None


def send_command(ser: Optional[serial.Serial], command: str) -> None:
    """
    Send command to Arduino.
    
    Args:
        ser: Serial object
        command: Command string
    """
    if ser and ser.is_open:
        ser.write(f"{command}\n".encode('utf-8'))
        print(f"→ Command: {command}")