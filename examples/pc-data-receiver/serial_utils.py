import serial
import serial.tools.list_ports
import json
import time

class SerialConnection:
    def __init__(self, port=None, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None

    def auto_detect_port(self):
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            if 'Arduino' in port.description or 'ACM' in port.description:
                print(f"Arduino found on port: {port.device}")
                return port.device
        print("Available COM ports:")
        for port in ports:
            print(f"  {port.device}: {port.description}")
        return None

    def connect(self):
        if not self.port:
            self.port = self.auto_detect_port()
            if not self.port:
                print("Arduino not found. Specify port manually.")
                return False
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2)
            print(f"Connection established: {self.port}")
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    def send_command(self, command):
        if self.ser and self.ser.is_open:
            self.ser.write(f"{command}\n".encode('utf-8'))
            print(f"Command sent: {command}")

    def read_json_message(self):
        if self.ser and self.ser.in_waiting > 0:
            try:
                line = self.ser.readline().decode('utf-8').strip()
                if line:
                    return json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None
        return None

    def close(self):
        if self.ser:
            self.ser.close()