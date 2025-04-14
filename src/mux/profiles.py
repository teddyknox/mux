#!/usr/bin/env python3

import json
import yaml
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Any

from .config import PROFILE_ENV_FILE_SUFFIX
from .exceptions import InvalidConfigError
from .ui import print_warning

# Functions for loading profile definitions from different sources.

def parse_env_file(file_path: Path) -> Dict[str, str]:
    """Parses a simple KEY=VALUE file, ignoring comments and empty lines."""
    env = {}
    try:
        with file_path.open('r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    env[key.strip()] = value.strip()
                # else: handle lines without '='? For now, ignore.
    except Exception as e:
        # Wrap generic file read errors
        raise InvalidConfigError(f"Error reading env file: {e}", str(file_path))
    return env

def load_profiles_from_files(profiles_dir: Path) -> Dict[str, Dict]:
    """Loads profiles from individual .env files in a 'profiles' directory."""
    profiles = {}
    if not profiles_dir.is_dir():
        return profiles # Return empty if dir doesn't exist
        
    for item in profiles_dir.iterdir():
        if item.is_file() and item.name.endswith(PROFILE_ENV_FILE_SUFFIX):
            profile_name = item.name[:-len(PROFILE_ENV_FILE_SUFFIX)] # Remove suffix
            if profile_name:
                try:
                    profiles[profile_name] = parse_env_file(item)
                except InvalidConfigError as e:
                    print_warning(f"Skipping profile '{profile_name}' due to error: {e}")
    return profiles


def load_profiles_from_yaml(yaml_file: Path) -> Optional[Dict[str, Dict]]:
    """Loads profiles from a profiles.yaml file. Returns None if file not found."""
    if not yaml_file.is_file():
        # return profiles # Old: returned {} incorrectly
        return None
    profiles = {}
    try:
        with yaml_file.open('r') as f:
            data = yaml.safe_load(f)
            if data is None:
                return {}
            if not isinstance(data, dict):
                raise InvalidConfigError("YAML root must be a dictionary (mapping profile names to env vars)", str(yaml_file))
            # Basic validation: ensure values are dictionaries
            for name, env_vars in data.items():
                if not isinstance(env_vars, dict):
                     raise InvalidConfigError(f"Value for profile '{name}' must be a dictionary of environment variables", str(yaml_file))
                # Ensure values are strings (or reasonably convertible)
                profiles[name] = {str(k): str(v) for k, v in env_vars.items()}
    except yaml.YAMLError as e:
        raise InvalidConfigError(f"Error parsing YAML: {e}", str(yaml_file))
    except Exception as e:
        # Catch other potential errors like file read issues
        raise InvalidConfigError(f"Error reading YAML file: {e}", str(yaml_file))
    return profiles


def load_profiles_from_script(script_path: Path, parent_profile: Optional[str] = None) -> Optional[Dict[str, Dict[str, str]]]:
    """Executes a profiles.py script and parses its JSON output."""
    if not script_path.is_file():
        return None

    command = [sys.executable, script_path]
    if parent_profile:
        command.append(parent_profile)
        
    try:
        # Use sys.executable to ensure the script is run with Python
        result = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            check=False, # Don't raise exception on non-zero exit code
            timeout=5 # Add a timeout for safety
        )

        if result.returncode != 0:
            # print_warning(f"Warning: Error executing profile script {script_path}") # Old warning
            print_warning(f"Profile script \n'{script_path}' failed (exit code\n{result.returncode}):\nStderr:\n{result.stderr.strip()}\n")
            return None

        try:
            profiles = json.loads(result.stdout)
            if not isinstance(profiles, dict):
                # print_warning(f"Warning: Invalid JSON structure from {script_path}") # Old warning
                print_warning(f"Configuration error in profile script \n'{script_path}': Script output\nmust be a JSON dictionary (mapping profile names to env vars)")
                return None
            # Basic validation of inner structure (optional but good)
            for name, env_vars in profiles.items():
                if not isinstance(env_vars, dict):
                     print_warning(f"Configuration error in profile script \n'{script_path}': Value for profile '{name}' must be a dictionary of env vars.")
                     return None # Or skip this profile?
            return profiles
        except json.JSONDecodeError as e:
            # print_warning(f"Warning: Could not parse JSON output from {script_path}") # Old warning
            print_warning(f"Configuration error in profile script \n'{script_path}': Error \ndecoding JSON from script: {e}\nOutput:\n{result.stdout.strip()}\n")
            return None

    except FileNotFoundError:
        # This shouldn't happen if script_path.is_file() passed, but handle defensively
        print_warning(f"Profile script '{script_path}' not found.")
        return None
    except subprocess.TimeoutExpired:
        print_warning(f"Profile script '{script_path}' timed out after 5 seconds.")
        return None
    except Exception as e:
        # Catch other potential errors during subprocess execution
        print_warning(f"Error running profile script \n'{script_path}': {e}")
        return None

def load_profiles_for_dimension(dim_path: Path, parent_profile: Optional[str] = None, silent: bool = False) -> Dict[str, Dict]:
    """
    Detects and loads profiles for a given dimension path using the first available method.
    Order: Dynamic (script) > YAML (profiles.yaml) > Manual (profiles/*.env)
    
    Args:
        dim_path: Path to the dimension directory
        parent_profile: Optional parent profile name (for script execution)
        silent: If True, suppresses informational warnings about loaded sources
    """
    profiles = None # Start with None to distinguish no source vs. empty source
    loaded_source = None # Track where profiles came from

    # 1. Try loading from profiles.py (Dynamic)
    profiles_py = dim_path / "profiles.py"
    try:
        # load_profiles_from_script returns None on error, or a dict (possibly empty) on success
        profiles = load_profiles_from_script(profiles_py, parent_profile)
        if profiles is not None: # Check if script ran successfully (even if it returned {}) 
            loaded_source = "script"
    except Exception as e:
        # Catch unexpected errors during script loading call itself
        print_warning(f"Unexpected error loading profiles from script '{profiles_py}': {e}")
        profiles = None # Reset on unexpected error

    # 2. If not loaded, try profiles.yaml
    profiles_yaml = dim_path / "profiles.yaml"
    if loaded_source is None: # Check if profiles is still None
        try:
            profiles = load_profiles_from_yaml(profiles_yaml)
            if profiles is not None: # Check if YAML loaded successfully (even if empty)
                loaded_source = "yaml"
        except InvalidConfigError as e:
             print_warning(f"Error loading profiles from YAML '{profiles_yaml}': {e}")
             profiles = None # Reset profiles on error
        except Exception as e:
            print_warning(f"Unexpected error loading profiles from YAML '{profiles_yaml}': {e}")
            profiles = None # Reset on unexpected error

    # 3. If not loaded, try loading from profiles/ directory (Manual)
    profiles_dir = dim_path / "profiles"
    if loaded_source is None: # Check if profiles is still None
        try:
            profiles = load_profiles_from_files(profiles_dir)
            if profiles is not None: # Check if files loaded successfully (even if empty)
                loaded_source = "files"
        except InvalidConfigError as e:
            print_warning(f"Error loading profiles from directory '{profiles_dir}': {e}")
            profiles = None # Reset profiles on error
        except Exception as e:
            print_warning(f"Unexpected error loading profiles from directory '{profiles_dir}': {e}")
            profiles = None # Reset on unexpected error


    # Optionally print info about which source was used
    if loaded_source and not silent:
        print_warning(f"Loaded profiles for '{dim_path.name}' from {loaded_source}.")
    elif not profiles_py.exists() and not profiles_yaml.exists() and not profiles_dir.exists() and not silent:
        print_warning(f"No profile source found for dimension '{dim_path.name}'.")

    # Return the loaded profiles dict, or an empty dict if no source was found/loaded
    return profiles if profiles is not None else {}

