"""
Configuration constants for Arduino collector.
"""

# Database defaults
DEFAULT_DB_PATH = "./arduino_data.db"

# Serial communication
DEFAULT_BAUDRATE = 115200
READ_SLEEP = 0.0001  # 1ms sleep in read loop

# Fall monitoring
DEFAULT_TIMEOUT_US = 1000000         # 1000 microseconds
DEFAULT_CHECK_INTERVAL_US = 1000000  # 1000 microseconds

AUTO_STOP = 10

# Logging
LOG_DIR = "logs"