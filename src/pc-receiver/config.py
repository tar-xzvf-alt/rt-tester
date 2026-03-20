"""
Configuration constants for Arduino collector.
"""

# Database defaults
DEFAULT_DB_PATH = "./arduino_data.db"

# Serial communication
DEFAULT_BAUDRATE = 115200
READ_SLEEP = 0.0001  # 1ms sleep in read loop

# Fall monitoring
DEFAULT_TIMEOUT_US = 2000000         # 2 seconds
DEFAULT_CHECK_INTERVAL_US = 2000000  # 2 seconds

AUTO_STOP = 1000

# Logging
LOG_DIR = "logs"