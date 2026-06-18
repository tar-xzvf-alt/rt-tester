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
                value = value.split('#', 1)[0].strip()
                
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
    """
    # Default values
    config_dict = {
        'db': config.DEFAULT_DB_PATH,
        'timeout-us': None,
        'check-interval-us': None,
        'auto-stop-groups': config.AUTO_STOP,
        'measurements-per-group': config.DEFAULT_MEASUREMENTS_PER_GROUP,
        'measurement-interval-us': config.DEFAULT_MEASUREMENT_INTERVAL_US,
        'target-board': config.DEFAULT_TARGET_BOARD,
        'target-kernel': config.DEFAULT_TARGET_KERNEL,
        'target-stress': config.DEFAULT_TARGET_STRESS,
        'target-payload': config.DEFAULT_TARGET_PAYLOAD,
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
            for key in ['db', 'timeout-us', 'check-interval-us', 'auto-stop-groups',
                        'measurements-per-group', 'measurement-interval-us',
                        'target-board', 'target-kernel', 'target-stress',
                        'target-payload']:
                if key in file_config:
                    config_dict[key] = file_config[key]
            
            # Validate stress value
            stress = str(config_dict['target-stress']).lower()
            if stress not in ['on', 'off', 'yes', 'no', 'true', 'false', '1', '0']:
                print(f"Warning: Invalid stress value '{config_dict['target-stress']}', using 'off'")
                config_dict['target-stress'] = 'off'
            else:
                # Normalize to 'on' or 'off'
                if stress in ['on', 'yes', 'true', '1']:
                    config_dict['target-stress'] = 'on'
                else:
                    config_dict['target-stress'] = 'off'

            # Validate payload value
            payload = str(config_dict['target-payload']).lower()
            if payload not in ['on', 'off', 'yes', 'no', 'true', 'false', '1', '0']:
                print(f"Warning: Invalid payload value '{config_dict['target-payload']}', using 'off'")
                config_dict['target-payload'] = 'off'
            else:
                if payload in ['on', 'yes', 'true', '1']:
                    config_dict['target-payload'] = 'on'
                else:
                    config_dict['target-payload'] = 'off'
            
            # Update soc section if present
            if 'soc' in file_config:
                soc_config = file_config['soc']
                if (soc_config.get('host') and 
                    soc_config.get('username') and 
                    soc_config.get('password')):
                    config_dict['soc'].update(soc_config)
                    config_dict['soc']['enabled'] = True
            
            print(f"Loaded configuration from: {config_path}")
            print(f"  db = {config_dict['db']}")
            print(f"  measurements-per-group = {config_dict['measurements-per-group']}")
            print(f"  measurement-interval-us = {config_dict['measurement-interval-us']} µs")
            print(f"  target-board = {config_dict['target-board']}")
            print(f"  target-kernel = {config_dict['target-kernel']}")
            print(f"  target-stress = {config_dict['target-stress']}")
            print(f"  target-payload = {config_dict['target-payload']}")
            
            if config_dict['auto-stop-groups']:
                print(f"  auto-stop-groups = {config_dict['auto-stop-groups']} groups")
            else:
                print(f"  auto-stop-groups = disabled")
            
        except Exception as e:
            print(f"Warning: Error loading config: {e}")
            print("  Using default values")
    
    return config_dict
