"""
Configuration constants for Arduino collector.
"""

# Database defaults
DEFAULT_DB_PATH = "arduino_data.db"

# Serial communication
DEFAULT_BAUDRATE = 115200
SERIAL_TIMEOUT = 1  # seconds
READ_SLEEP = 0.001  # seconds

# Fall monitoring defaults
DEFAULT_TIMEOUT_US = 10_000_000  # 10 seconds
DEFAULT_CHECK_INTERVAL_US = 2_000_000  # 2 seconds

# Logging
LOG_DIR = "logs"