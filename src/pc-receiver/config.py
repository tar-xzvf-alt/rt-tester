"""
Configuration constants for Arduino collector.
"""

import os

# Database defaults
DEFAULT_DB_PATH = "./arduino_data.db"

# Serial communication
DEFAULT_BAUDRATE = 115200
READ_SLEEP = 0.0001  # 1ms sleep in read loop

# Fall monitoring
DEFAULT_TIMEOUT_US = 2000000         # 2 seconds
DEFAULT_CHECK_INTERVAL_US = 2000000  # 2 seconds

# Measurement parameters
DEFAULT_WORST_COUNT = 75
DEFAULT_MEASUREMENT_INTERVAL_US = 300
DEFAULT_MEASUREMENTS_PER_GROUP = 1500
DEFAULT_RESPONSE_TIMEOUT_US = 10000

# Target device information
DEFAULT_TARGET_BOARD = "unknown"
DEFAULT_TARGET_KERNEL = "unknown"
DEFAULT_TARGET_STRESS = "off"  # on - stress applied, off - no stress
DEFAULT_TARGET_PAYLOAD = "off"  # on - payload between pulses, off - idle between pulses

AUTO_STOP = 2500

# Logging
STATE_DIR = os.environ.get(
    "RT_TESTER_STATE_DIR",
    os.path.join(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
                 "rt-tester"),
)
LOG_DIR = os.path.join(STATE_DIR, "logs")
METRICS_LOG = os.path.join(STATE_DIR, "metrics_all_groups.log")
