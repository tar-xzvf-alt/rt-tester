"""
Logging utilities for Arduino collector.
"""

import logging
import os
from typing import Optional
from config import LOG_DIR


def setup_session_logging(session_id: int) -> Optional[logging.Logger]:
    """
    Set up a separate log file for a specific session.
    
    Args:
        session_id: Session identifier
    
    Returns:
        Logger instance configured for the session
    """
    if session_id is None:
        return None
    
    # Create logs directory if it doesn't exist
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Create logger for this session
    logger = logging.getLogger(f"session_{session_id}")
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create file handler
    log_file = os.path.join(LOG_DIR, f"session_{session_id}.log")
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(file_handler)
    
    return logger