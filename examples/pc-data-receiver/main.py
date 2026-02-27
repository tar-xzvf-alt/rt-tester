from arduino_data_receiver import ArduinoDataReceiver

def main():
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