import time
from serial_utils import SerialConnection
from data_utils import DataManager
from plot_utils import generate_mixed_plots, create_summary_plot
from interactive_utils import interactive_loop

class ArduinoDataReceiver:
    def __init__(self, port=None, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.conn = None
        self.data_manager = DataManager()
        self.last_data_received = None

    def connect(self):
        self.conn = SerialConnection(self.port, self.baudrate)
        return self.conn.connect()

    def send_command(self, command):
        if self.conn:
            self.conn.send_command(command)

    def read_json_message(self):
        if self.conn:
            return self.conn.read_json_message()
        return None

    def start_measurement(self):
        self.send_command("START")

    def request_data(self):
        self.send_command("SEND")
        self.wait_and_process_data()

    def wait_and_process_data(self, timeout=10):
        start_time = time.time()
        print("Waiting for data from Arduino...")
        while time.time() - start_time < timeout:
            msg = self.read_json_message()
            if msg:
                if "avg_latency_us" in msg:
                    self.data_manager.process_mixed_data(msg)
                    return True
                else:
                    status = msg.get('status', '')
                    if status == 'data_ready':
                        print(f"✓ [ARDUINO] {msg.get('message', '')}")
                    elif status == 'sending':
                        print(f"✓ [ARDUINO] {msg.get('message', '')}")
                    elif status == 'error':
                        print(f"✗ [ARDUINO] {msg.get('message', '')}")
            time.sleep(0.1)
        print("Timeout waiting for data!")
        return False

    def get_status(self):
        self.send_command("STATUS")

    def reset(self):
        self.send_command("RESET")

    def process_data_with_plot(self, data):
        if "avg_latency_us" in data:
            self.data_manager.process_mixed_data(data)
        else:
            print("Unknown data format")
            return False

    def generate_plots(self, data):
        generate_mixed_plots(data)

    def save_data(self, data):
        self.data_manager.save_mixed_data_to_file(data)

    def interactive_mode(self):
        interactive_loop(self)

    def create_summary_plot(self):
        if self.data_manager.data:
            create_summary_plot(self.data_manager.data)
        else:
            print("No data for summary plot")