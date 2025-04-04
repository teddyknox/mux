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


def load_profiles_from_yaml(yaml_file: Path) -> Dict[str, Dict]:
    """Loads profiles from a profiles.yaml file."""
    profiles = {}
    if not yaml_file.is_file():
        return profiles
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


def load_profiles_from_script(script_file: Path, parent_profile: Optional[str] = None) -> Dict[str, Dict]:
    """Loads profiles by executing a profiles.py script."""
    profiles = {}
    if not script_file.is_file() or not os.access(script_file, os.X_OK):
        if script_file.is_file():
             print_warning(f"Profile script '{script_file}' is not executable. Skipping.")
        return profiles

    cmd = [str(script_file)]
    # Pass parent profile as first argument if provided (as per original design idea)
    # Note: This relies on the script expecting this argument.
    if parent_profile:
        cmd.append(parent_profile)
        
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=5) # Added timeout
        try:
            data = json.loads(result.stdout)
            if not isinstance(data, dict):
                 raise InvalidConfigError("Script output must be a JSON dictionary (mapping profile names to env vars)", str(script_file))
             # Basic validation: ensure values are dictionaries and content are strings
            for name, env_vars in data.items():
                if not isinstance(env_vars, dict):
                     raise InvalidConfigError(f"Value for profile '{name}' in script output must be a dictionary of environment variables", str(script_file))
                profiles[name] = {str(k): str(v) for k, v in env_vars.items()}
        except json.JSONDecodeError as e:
            raise InvalidConfigError(f"Error decoding JSON from script: {e}\nOutput:\n{result.stdout}", str(script_file))

    except FileNotFoundError:
        # Should not happen if is_file() and access() passed, but defensive
        print_warning(f"Profile script '{script_file}' not found during execution. Skipping.")
    except subprocess.CalledProcessError as e:
        print_warning(f"Profile script '{script_file}' failed (exit code {e.returncode}):\nStderr:\n{e.stderr}")
    except subprocess.TimeoutExpired:
        print_warning(f"Profile script '{script_file}' timed out after 5 seconds. Skipping.")
    except InvalidConfigError as e:
        # Re-raise config errors specifically so tests can catch them
        raise e
    except Exception as e:
        # Catch other potential errors
        print_warning(f"Error running profile script '{script_file}': {e}")

    return profiles

def load_profiles_for_dimension(dim_path: Path, parent_dim: Optional[Any] = None) -> Dict[str, Dict]:
    """
    Detects and loads profiles for a given dimension path using the first available method.
    Order: files > yaml > script
    """
    profiles = {}
    loaded_source = None # Track where profiles came from

    # 1. Try loading from profiles/ directory
    profiles_dir = dim_path / "profiles"
    try:
        profiles = load_profiles_from_files(profiles_dir)
        if profiles:
            loaded_source = "files"
    except InvalidConfigError as e:
         print_warning(f"Error loading profiles from directory '{profiles_dir}': {e}")
         profiles = {} # Reset profiles on error

    # 2. If not loaded, try profiles.yaml
    profiles_yaml = dim_path / "profiles.yaml"
    if not loaded_source:
        try:
            profiles = load_profiles_from_yaml(profiles_yaml)
            if profiles:
                loaded_source = "yaml"
        except InvalidConfigError as e:
             print_warning(f"Error loading profiles from YAML '{profiles_yaml}': {e}")
             profiles = {} # Reset profiles on error

    # 3. If not loaded, try profiles.py
    profiles_py = dim_path / "profiles.py"
    if not loaded_source:
        parent_profile_name = None # TODO: Get parent profile name if needed and parent_dim exists
        # If parent_dim and hasattr(parent_dim, 'get_active_profile_name'): # Example check
        #     parent_profile_name = parent_dim.get_active_profile_name()
        try:
            profiles = load_profiles_from_script(profiles_py, parent_profile_name)
            if profiles:
                 loaded_source = "script"
        except InvalidConfigError as e:
             # Warnings are printed inside load_profiles_from_script for execution errors
             # Re-raising here allows tests to catch config errors, but we still warn.
             print_warning(f"Configuration error in profile script '{profiles_py}': {e}")
             profiles = {} # Reset profiles on error
             # Re-raise the error for testing/handling higher up?
             # raise e 
        except Exception as e:
             # Catch unexpected errors during script loading call itself
             print_warning(f"Unexpected error loading profiles from script '{profiles_py}': {e}")
             profiles = {} # Reset profiles on error

    # Optionally print info about which source was used
    # if loaded_source:
    #     print_info(f"Loaded profiles for '{dim_path.name}' from {loaded_source}.")
    # elif not profiles_dir.exists() and not profiles_yaml.exists() and not profiles_py.exists():
    #     print_info(f"No profile source found for dimension '{dim_path.name}'.")

    return profiles

