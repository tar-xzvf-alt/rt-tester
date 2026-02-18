import serial
import json
import time
import pandas as pd
from datetime import datetime
import matplotlib as mpl
import matplotlib.pyplot as plt
import os

mpl.use("agg")

class ArduinoDataReceiver:
    def __init__(self, port=None, baudrate=115200):
        """Initialize connection with Arduino"""
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.data = []
        self.session_id = None
        self.last_data_received = None
        
    def auto_detect_port(self):
        """Automatically detect Arduino port"""
        import serial.tools.list_ports
        
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
        """Establish connection with Arduino"""
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
        """Send command to Arduino"""
        if self.ser and self.ser.is_open:
            self.ser.write(f"{command}\n".encode('utf-8'))
            print(f"Command sent: {command}")
    
    def read_json_message(self):
        """Read JSON message from Arduino"""
        if self.ser and self.ser.in_waiting > 0:
            try:
                line = self.ser.readline().decode('utf-8').strip()
                if line:
                    return json.loads(line)
            except json.JSONDecodeError:
                return None
            except UnicodeDecodeError:
                return None
        return None
    
    def start_measurement(self):
        """Start measurements"""
        self.send_command("START")
    
    def request_data(self):
        """Request measurement data and automatically generate plots"""
        self.send_command("SEND")
        self.wait_and_process_data()
    
    def wait_and_process_data(self, timeout=10):
        """Wait for data and automatically process"""
        start_time = time.time()
        print("Waiting for data from Arduino...")
        
        while time.time() - start_time < timeout:
            message = self.read_json_message()
            if message:
                if "avg_latency_us" in message:
                    self.process_data_with_plot(message)
                    return True
                else:
                    status = message.get('status', '')
                    if status == 'data_ready':
                        print(f"✓ [ARDUINO] {message.get('message', '')}")
                    elif status == 'sending':
                        print(f"✓ [ARDUINO] {message.get('message', '')}")
                    elif status == 'error':
                        print(f"✗ [ARDUINO] {message.get('message', '')}")
            
            time.sleep(0.1)
        
        print("Timeout waiting for data!")
        return False
    
    def get_status(self):
        """Get status"""
        self.send_command("STATUS")
    
    def reset(self):
        """Reset measurements"""
        self.send_command("RESET")
    
    def process_data_with_plot(self, data):
        """Process received data and automatically generate plots"""
        if "avg_latency_us" in data:
            self.process_mixed_data(data)
        else:
            print("Unknown data format")
            return False
    
    def process_mixed_data(self, data):
        if "session_id" in data:
            self.session_id = data["session_id"]
        
        # Save last data
        self.last_data_received = data
        
        # Save averaged data
        measurements = {
            'session_id': data.get('session_id', 'unknown'),
            'timestamp': datetime.now(),
            'avg_latency_us': data.get('avg_latency_us', []),
            'min_latency_us': data.get('min_latency_us', []),
            'max_latency_us': data.get('max_latency_us', []),
            'avg_jitter_us': data.get('avg_jitter_us', []),
            'statistics': data.get('statistics', {})
        }
        
        self.data.append(measurements)
        
        # Get measurement parameters
        params = data.get('parameters', {})
        delay_between_pulses = params.get('delay_between_pulses_us', 0)
        groups_count = data.get('groups_count', 0)
        measurements_per_group = data.get('measurements_per_group', 0)
        
        # Display statistics
        stats = data.get('statistics', {})
        if stats:
            print("\n" + "="*60)
            print(f"SESSION: {data.get('session_id', 'N/A')}")
            print(f"CONFIGURATION: {groups_count} groups × {measurements_per_group} measurements")
            print(f"PULSE DELAY: {delay_between_pulses:,} µs")
            print(f"TIME: {datetime.now().strftime('%H:%M:%S')}")
            print("-"*60)
            
            latency_stats = stats.get('latency', {})
            if latency_stats:
                print("LATENCY STATISTICS (µs):")
                print(f"  OVERALL AVG: {latency_stats.get('overall_avg_us', 0):.2f}")
                print(f"  OVERALL MIN: {latency_stats.get('overall_min_us', 0):.2f}")
                print(f"  OVERALL MAX: {latency_stats.get('overall_max_us', 0):.2f}")
                print(f"  VARIATION: {latency_stats.get('variation_us', 0):.2f}")
            
            jitter_stats = stats.get('jitter', {})
            if jitter_stats:
                print(f"\nJITTER STATISTICS (µs):")
                print(f"  OVERALL AVG: {jitter_stats.get('overall_avg_us', 0):.2f}")
            print("="*60 + "\n")
        
        # Automatically generate plots
        self.generate_mixed_plots(data)
        
        # Save to file
        self.save_mixed_data_to_file(data)
        
        return True
    
    def generate_mixed_plots(self, data):
        try:
            # Check for required data
            if "avg_latency_us" not in data:
                print("No data for plotting")
                return
            
            avg_latency = data['avg_latency_us']
            min_latency = data['min_latency_us']
            max_latency = data['max_latency_us']
            avg_jitter = data['avg_jitter_us']
            
            # Get overall averages from statistics
            stats = data.get('statistics', {})
            total_avg_latency = stats.get('latency', {}).get('overall_avg_us', 0)
            total_avg_jitter = stats.get('jitter', {}).get('overall_avg_us', 0)
            
            # Get measurement parameters
            params = data.get('parameters', {})
            delay_between_pulses = params.get('delay_between_pulses_us', 0)
            groups_count = data.get('groups_count', 0)
            measurements_per_group = data.get('measurements_per_group', 0)
            
            # Create directory if it doesn't exist
            data_dir = "arduino_measurements"
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)
            
            # Create 2 plots (1x2)
            fig, axes = plt.subplots(1, 2, figsize=(14, 6))
            
            session_id = data.get('session_id', 'unknown')
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Updated title with delay_between_pulses
            fig.suptitle(f'Latency & Jitter Analysis | Session: {session_id}\n'
                        f'Delay: {delay_between_pulses:,} µs | {timestamp}', 
                        fontsize=14, fontweight='bold')
            
            # Import necessary module
            from matplotlib.ticker import MaxNLocator
            
            # 1. Latency plot with min-max range
            if len(avg_latency) > 0:
                # Explicitly create list of integers for groups
                groups = list(range(1, len(avg_latency) + 1))
                
                # Main line - average values
                line1 = axes[0].plot(groups, avg_latency, 'b.-', markersize=8, linewidth=2, 
                                label=f'Average latency per group')[0]
                
                # Min-max range (fill)
                fill = axes[0].fill_between(groups, min_latency, max_latency, 
                                        alpha=0.2, color='blue', label='Min-max range')
                
                # Min and max points
                scatter_min = axes[0].scatter(groups, min_latency, color='green', s=20, 
                                            marker='^', alpha=0.6, label=f'Min: {min(min_latency):.1f} µs')
                scatter_max = axes[0].scatter(groups, max_latency, color='red', s=20, 
                                            marker='v', alpha=0.6, label=f'Max: {max(max_latency):.1f} µs')
                
                # Overall average latency line (horizontal)
                axes[0].axhline(y=total_avg_latency, color='black', linestyle='--', 
                            linewidth=2, alpha=0.7, 
                            label=f'Overall avg: {total_avg_latency:.1f} µs')
                
                # Set integer ticks on X axis
                axes[0].xaxis.set_major_locator(MaxNLocator(integer=True))
                axes[0].set_xticks(groups)  # Explicitly set tick positions
                
                # Updated title for first plot with group information
                axes[0].set_title(f'Latency per group ({groups_count}×{measurements_per_group} measurements)', 
                                fontsize=12)
                axes[0].set_xlabel('Group number')
                axes[0].set_ylabel('Latency (µs)')
                axes[0].grid(True, alpha=0.3)
                axes[0].legend(loc='best', fontsize=9)
            
            # 2. Average jitter plot (simple line)
            if len(avg_jitter) > 0:
                # Use same groups list
                groups = list(range(1, len(avg_jitter) + 1))
                
                # Simple line for average jitter
                line2 = axes[1].plot(groups, avg_jitter, 'g.-', markersize=8, linewidth=2,
                                label='Average jitter per group')[0]
                
                # Overall average jitter line (horizontal)
                axes[1].axhline(y=total_avg_jitter, color='black', linestyle='--', 
                            linewidth=2, alpha=0.7,
                            label=f'Overall avg: {total_avg_jitter:.1f} µs')
                
                # Set integer ticks on X axis
                axes[1].xaxis.set_major_locator(MaxNLocator(integer=True))
                axes[1].set_xticks(groups)  # Explicitly set tick positions
                
                # Updated title for second plot
                axes[1].set_title(f'Jitter per group ({groups_count}×{measurements_per_group} measurements)', 
                                fontsize=12)
                axes[1].set_xlabel('Group number')
                axes[1].set_ylabel('Jitter (µs)')
                axes[1].grid(True, alpha=0.3)
                axes[1].legend(loc='best', fontsize=9)
            
            plt.tight_layout(rect=[0, 0, 1, 0.93])  # Slightly increased top margin for title
            
            # Save plot
            timestamp_file = datetime.now().strftime("%Y%m%d_%H%M%S")
            plot_filename = f"{data_dir}/latency_jitter_session_{session_id}_{timestamp_file}.png"
            plt.savefig(plot_filename, dpi=150)
            print(f"✓ Plots saved: {plot_filename}")
            
            # Show plots
            plt.show(block=False)
            plt.pause(0.1)
            
            # Close figure
            time.sleep(3)
            plt.close(fig)
            
        except Exception as e:
            print(f"Error generating plots: {e}")
            
    def save_mixed_data_to_file(self, data):
        """Save data to files"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_id = data.get('session_id', 'unknown')
            
            # Create directory
            data_dir = "arduino_measurements"
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)
            
            # Save JSON
            json_filename = f"{data_dir}/latency_jitter_session_{session_id}_{timestamp}.json"
            with open(json_filename, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"✓ JSON saved: {json_filename}")
            
            # Save CSV if data exists
            if all(key in data for key in ['avg_latency_us', 'min_latency_us', 'max_latency_us',
                                          'avg_jitter_us']):
                groups_count = len(data['avg_latency_us'])
                df_data = {
                    'group_num': list(range(1, groups_count + 1)),
                    'avg_latency_us': data['avg_latency_us'],
                    'min_latency_us': data['min_latency_us'],
                    'max_latency_us': data['max_latency_us'],
                    'latency_variation_us': [max_val - min_val for max_val, min_val in 
                                           zip(data['max_latency_us'], data['min_latency_us'])],
                    'avg_jitter_us': data['avg_jitter_us']
                }
                
                df = pd.DataFrame(df_data)
                csv_filename = f"{data_dir}/latency_jitter_session_{session_id}_{timestamp}.csv"
                df.to_csv(csv_filename, index=False)
                print(f"✓ CSV saved: {csv_filename}")
                
        except Exception as e:
            print(f"Error saving files: {e}")
    
    def interactive_mode(self):
        """Interactive control mode"""
        print("\n" + "="*60)
        print("ARDUINO INTERACTIVE CONTROL MODE")
        print("="*60)
        print("Commands: start, send, status, reset, summary, save, help, exit")
        print("="*60)
        
        try:
            while True:
                # Read messages from Arduino
                message = self.read_json_message()
                if message:
                    status = message.get('status', '')
                    
                    if status == 'data_ready':
                        print(f"\n✓ [ARDUINO] {message.get('message', '')}")
                        print("   Use 'send' to retrieve data and plots")
                    elif status == 'started':
                        print(f"\n✓ [ARDUINO] {message.get('message', '')}")
                    elif status == 'sending':
                        print(f"\n✓ [ARDUINO] {message.get('message', '')}")
                    elif status == 'error':
                        print(f"\n✗ [ARDUINO] Error: {message.get('message', '')}")
                    elif "avg_latency_us" in message:
                        print("\n✓ [ARDUINO] Measurement data received!")
                        # Automatic processing
                        self.process_data_with_plot(message)
                
                # Check user input
                cmd = input("\nEnter command: ").strip().lower()
                
                if cmd == "start":
                    self.start_measurement()
                elif cmd == "send":
                    print("Requesting data...")
                    self.request_data()
                elif cmd == "status":
                    self.get_status()
                elif cmd == "reset":
                    self.reset()
                elif cmd == "summary":
                    self.create_summary_plot()
                elif cmd == "save" and self.data:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    all_data_filename = f"arduino_measurements/all_sessions_{timestamp}.json"
                    with open(all_data_filename, 'w') as f:
                        json.dump(self.data, f, indent=2)
                    print(f"✓ All data saved: {all_data_filename}")
                elif cmd == "help":
                    print("\n" + "="*40)
                    print("COMMANDS:")
                    print("="*40)
                    print("start   - Start measurements")
                    print("send    - Get data and plots (AUTOMATIC)")
                    print("status  - Measurement status")
                    print("reset   - Reset measurements")
                    print("summary - Session comparison plot")
                    print("save    - Save all data")
                    print("exit    - Exit")
                    print("="*40)
                elif cmd == "exit":
                    print("\nExiting...")
                    break
                else:
                    print("Unknown command. Type 'help'")
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\nInterrupted by user")
        except Exception as e:
            print(f"\nError: {e}")
        finally:
            if self.ser:
                self.ser.close()
                print("Connection closed")
    
    def create_summary_plot(self):
        if not self.data:
            print("No data for summary plot")
            return
        
        try:
            fig, axes = plt.subplots(1, 2, figsize=(14, 6))
            
            # Import necessary module
            from matplotlib.ticker import MaxNLocator
            
            for i, session in enumerate(self.data):
                session_id = session.get('session_id', f'Session_{i}')
                
                # Check data type
                if 'avg_latency_us' in session:
                    # Latency/Jitter data
                    avg_latency = session['avg_latency_us']
                    avg_jitter = session['avg_jitter_us']
                    
                    if avg_latency and len(avg_latency) > 0:
                        groups = list(range(1, len(avg_latency) + 1))
                        axes[0].plot(groups, avg_latency, '.-', 
                                    label=session_id, alpha=0.7)
                    
                    if avg_jitter and len(avg_jitter) > 0:
                        groups = list(range(1, len(avg_jitter) + 1))
                        axes[1].plot(groups, avg_jitter, '.-', 
                                    label=session_id, alpha=0.7)
            
            # Set integer ticks on both X axes
            axes[0].xaxis.set_major_locator(MaxNLocator(integer=True))
            axes[1].xaxis.set_major_locator(MaxNLocator(integer=True))
            
            axes[0].set_title('Average Latency Comparison Between Sessions')
            axes[0].set_xlabel('Group number')
            axes[0].set_ylabel('Latency (µs)')
            axes[0].legend()
            axes[0].grid(True, alpha=0.3)
            
            axes[1].set_title('Average Jitter Comparison Between Sessions')
            axes[1].set_xlabel('Group number')
            axes[1].set_ylabel('Jitter (µs)')
            axes[1].legend()
            axes[1].grid(True, alpha=0.3)
            
            plt.tight_layout()
            
            # Save
            data_dir = "arduino_measurements"
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            plt.savefig(f"{data_dir}/summary_comparison_{timestamp}.png", dpi=150)
            plt.show(block=False)
            print("✓ Summary plot saved")
            
            time.sleep(3)
            plt.close()
            
        except Exception as e:
            print(f"Error generating summary plot: {e}")

def main():
    """Main function"""
    print("="*60)
    print("ARDUINO <-> LICHEE MEASUREMENT SYSTEM")
    print("="*60)
    print("Automatic plot generation with 'send' command")
    print("="*60)
    
    receiver = ArduinoDataReceiver()
    
    if not receiver.connect():
        port = input("Enter COM port manually: ")
        receiver.port = port
        if not receiver.connect():
            return
    
    receiver.interactive_mode()

if __name__ == "__main__":
    main()