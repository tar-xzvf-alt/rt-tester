"""
Fall monitoring functionality.
"""

import time
from datetime import datetime
from typing import Optional, Callable


class FallMonitor:
    """
    Monitor for system falls and recoveries.
    """
    
    def __init__(self, timeout_us: int, on_fall: Callable, on_recovery: Callable):
        """
        Initialize fall monitor.
        
        Args:
            timeout_us: Timeout in microseconds
            on_fall: Callback for fall detection
            on_recovery: Callback for recovery
        """
        self.timeout_us = timeout_us
        self.on_fall = on_fall
        self.on_recovery = on_recovery
        
        self.last_data_time_us = 0
        self.is_fallen = False
        self.fall_start_time_us = 0
    
    def update_last_data_time(self) -> None:
        """Update last data time to current time."""
        self.last_data_time_us = time.time_ns() // 1000
    
    def check(self, current_time_us: int) -> None:
        """
        Check if system has fallen.
        
        Args:
            current_time_us: Current time in microseconds
        """
        if self.last_data_time_us == 0:
            return
        
        time_since_last_data_us = current_time_us - self.last_data_time_us
        
        # Timeout exceeded and not yet fallen
        if time_since_last_data_us > self.timeout_us and not self.is_fallen:
            self.is_fallen = True
            self.fall_start_time_us = current_time_us
            self.on_fall(time_since_last_data_us)
        
        # Recovery after fall
        elif time_since_last_data_us <= self.timeout_us and self.is_fallen:
            self.is_fallen = False
            fall_duration_us = current_time_us - self.fall_start_time_us
            self.on_recovery(fall_duration_us)
    
    def reset(self) -> None:
        """Reset monitor state."""
        self.last_data_time_us = 0
        self.is_fallen = False
        self.fall_start_time_us = 0