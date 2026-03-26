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

# Measurement parameters
DEFAULT_WORST_COUNT = 125
DEFAULT_MEASUREMENT_INTERVAL_US = 300

# Target device information
DEFAULT_TARGET_BOARD = "unknown"
DEFAULT_TARGET_KERNEL = "unknown"
DEFAULT_TARGET_STRESS = "off"  # on - stress applied, off - no stress

AUTO_STOP = 2500

# Logging
LOG_DIR = "logs"