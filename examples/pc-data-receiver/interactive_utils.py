import time
import json
from datetime import datetime

def interactive_loop(receiver):
    print("\n" + "="*60)
    print("ARDUINO INTERACTIVE CONTROL MODE")
    print("="*60)
    print("Commands: start, send, status, reset, summary, save, help, exit")
    print("="*60)

    try:
        while True:
            # Читаем входящие сообщения от Arduino
            msg = receiver.read_json_message()
            if msg:
                status = msg.get('status', '')
                if status == 'data_ready':
                    print(f"\n✓ [ARDUINO] {msg.get('message', '')}")
                    print("   Use 'send' to retrieve data and plots")
                elif status == 'started':
                    print(f"\n✓ [ARDUINO] {msg.get('message', '')}")
                elif status == 'sending':
                    print(f"\n✓ [ARDUINO] {msg.get('message', '')}")
                elif status == 'error':
                    print(f"\n✗ [ARDUINO] Error: {msg.get('message', '')}")
                elif "avg_latency_us" in msg:
                    print("\n✓ [ARDUINO] Measurement data received!")
                    receiver.process_data_with_plot(msg)

            cmd = input("\nEnter command: ").strip().lower()

            if cmd == "start":
                receiver.start_measurement()
            elif cmd == "send":
                print("Requesting data...")
                receiver.request_data()
            elif cmd == "status":
                receiver.get_status()
            elif cmd == "reset":
                receiver.reset()
            elif cmd == "summary":
                receiver.create_summary_plot()
            elif cmd == "save" and receiver.data_manager.data:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"arduino_measurements/all_sessions_{timestamp}.json"
                with open(filename, 'w') as f:
                    json.dump(receiver.data_manager.data, f, indent=2)
                print(f"✓ All data saved: {filename}")
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
        if receiver.conn:
            receiver.conn.close()
            print("Connection closed")