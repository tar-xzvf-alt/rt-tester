#!/usr/bin/env python3
"""
Configuration loader for Arduino Data Collection Daemon.
Reads parameters from a simple text config file with sections.
"""

import os
import config

def parse_config_file(config_path):
    """
    Parse a key=value config file with [section] support.
    
    Args:
        config_path: Path to config file
        
    Returns:
        dict: Dictionary with configuration parameters (supports nested sections)
    """
    params = {}
    current_section = None
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Handle sections [section_name]
            if line.startswith('[') and line.endswith(']'):
                current_section = line[1:-1].strip()
                if current_section not in params:
                    params[current_section] = {}
                continue
            
            # Parse key=value
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Convert value based on content
                if value.isdigit():
                    converted_value = int(value)
                elif value.replace('.', '', 1).isdigit():
                    converted_value = float(value)
                elif value.lower() in ('true', 'false'):
                    converted_value = value.lower() == 'true'
                else:
                    # Expand user and variables in paths
                    value = os.path.expanduser(value)
                    value = os.path.expandvars(value)
                    converted_value = value
                
                # Store in appropriate section or global
                if current_section:
                    params[current_section][key] = converted_value
                else:
                    params[key] = converted_value
    
    return params


def load_config(config_path=None):
    """
    Load configuration from file or use defaults.
    
    Args:
        config_path: Optional path to config file
        
    Returns:
        dict: Complete configuration dictionary
    """
    # Default values
    config_dict = {
        'db': config.DEFAULT_DB_PATH,
        'timeout-us': config.DEFAULT_TIMEOUT_US,
        'check-interval-us': config.DEFAULT_CHECK_INTERVAL_US,
        'auto-stop-groups': config.AUTO_STOP,  # None means "do not stop automatically"
        'soc': {
            'enabled': False,
            'host': None,
            'port': 22,
            'username': None,
            'password': None
        }
    }
    
    if config_path:
        try:
            file_config = parse_config_file(config_path)
            
            # Update global parameters
            for key in ['db', 'timeout-us', 'check-interval-us', 'auto-stop-groups']:
                if key in file_config:
                    config_dict[key] = file_config[key]
            
            # Update soc section if present
            if 'soc' in file_config:
                soc_config = file_config['soc']
                # Only enable if we have minimum required params
                if (soc_config.get('host') and 
                    soc_config.get('username') and 
                    soc_config.get('password')):
                    config_dict['soc'].update(soc_config)
                    config_dict['soc']['enabled'] = True
            
            print(f"Loaded configuration from: {config_path}")
            print(f"  db = {config_dict['db']}")
            print(f"  timeout-us = {config_dict['timeout-us']:,} µs ({config_dict['timeout-us']/1_000_000:.1f} sec)")
            print(f"  check-interval-us = {config_dict['check-interval-us']:,} µs ({config_dict['check-interval-us']/1_000_000:.1f} sec)")
            
            if config_dict['auto-stop-groups']:
                print(f"  auto-stop-groups = {config_dict['auto-stop-groups']} groups")
            else:
                print(f"  auto-stop-groups = disabled")
            
            if config_dict['soc']['enabled']:
                print(f"  SoC monitoring: ENABLED")
                print(f"    host: {config_dict['soc']['host']}")
                print(f"    user: {config_dict['soc']['username']}")
            else:
                print(f"  SoC monitoring: DISABLED")
            
        except Exception as e:
            print(f"Warning: Error loading config: {e}")
            print("  Using default values")
    
    return config_dict