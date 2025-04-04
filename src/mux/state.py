import os
from typing import Dict, List, Optional, Tuple
import json # Used to store list of vars set by mux for a dimension

# Import necessary components from dimension module
from .utils import MUX_DIR_PATH # Import MUX_DIR_PATH if needed by find_dimensions
from .config import MUX_DIR # Use config directly

# Forward declaration for type hinting
class Dimension:
    # Adding attributes expected by the modified code
    name: str
    def get_env_vars(self, profile_name: str) -> Dict[str, str]: ...


# --- Environment Variable Naming ---

def get_active_profile_env_var(dim_name: str) -> str:
    """Returns the environment variable name storing the active profile for a dimension."""
    # Uppercase dimension name for the variable
    return f"MUX_ACTIVE_{dim_name.upper()}"

# New env var to track variables set by mux for a dimension
def get_managed_vars_env_var(dim_name: str) -> str:
    """Returns the environment variable storing the JSON list of var names managed by mux for this dimension."""
    return f"MUX_MANAGED_VARS_{dim_name.upper()}"


# --- Reading State ---

def get_active_profile(dim_name: str) -> Optional[str]:
    """Gets the currently active profile name for a dimension.

    Checks the environment variable first. If not set, checks if a default
    profile is configured via default.txt for the dimension and returns that if found.
    """
    # 1. Check environment variable
    env_var = get_active_profile_env_var(dim_name)
    active_profile = os.environ.get(env_var)
    if active_profile:
        return active_profile

    # 2. If no env var, check for default.txt
    try:
        # Construct path: ~/.mux/dims/<dim_name>/default.txt
        # Ensure dim_name doesn't contain path traversal chars (basic check)
        if '/' in dim_name or '\\' in dim_name or '.' in dim_name:
            # Avoid potential security issues with crafted dim_names
            return None
            
        # Use MUX_DIR from config
        dim_path = MUX_DIR / 'dims' / dim_name
        default_file = dim_path / "default.txt"
        if default_file.is_file():
            # Read the default profile name from the file
            with open(default_file, 'r') as f:
                default_profile_name = f.read().strip()
                if default_profile_name: # Ensure it's not empty
                    # We don't validate if the profile exists here, 
                    # relying on the caller (like Dimension class) to handle it.
                    return default_profile_name
    except FileNotFoundError:
        pass # Dimension directory might not exist
    except OSError as e:
        # Handle potential errors like permission issues reading the file
        pass # Fall through to return None
    except Exception as e:
        # Catch unexpected errors
        pass # Fall through to return None

    # 3. No active or default profile found
    return None

def get_currently_managed_vars(dim_name: str) -> List[str]:
    """Reads the list of variable names currently managed by mux for this dimension from the environment."""
    managed_vars_env_var = get_managed_vars_env_var(dim_name)
    managed_vars_json = os.environ.get(managed_vars_env_var)
    if managed_vars_json:
        try:
            return json.loads(managed_vars_json)
        except json.JSONDecodeError:
            # Handle corrupted JSON data, perhaps log a warning
            return []
    return []


# --- Modifying State (Generating Shell Commands) ---

def generate_activate_commands(dimension: Dimension, profile_name: str) -> List[str]:
    """
    Generates shell commands to deactivate the current profile (if any)
    and activate the new profile for the given dimension using original variable names.
    """
    commands = []
    dim_name = dimension.name
    new_env_vars = dimension.get_env_vars(profile_name)

    # 1. Get the list of variable names managed by the *currently active* profile (if any)
    currently_managed_vars = get_currently_managed_vars(dim_name)

    # 2. Generate unset commands for all variables managed by the previous profile
    for var_name in currently_managed_vars:
        # Check if the variable still exists before unsetting, avoids errors if manually unset
        commands.append(f"unset {var_name}")

    # 3. Generate export commands for the *new* profile's variables (using original names)
    newly_managed_vars = []
    for var_name, var_value in new_env_vars.items():
        # Ensure proper quoting for values with spaces or special chars
        quoted_value = f"'{var_value.replace("'", "'\\''")}'"
        commands.append(f"export {var_name}={quoted_value}")
        newly_managed_vars.append(var_name) # Keep track of vars set by this profile

    # 4. Update the marker for variables managed by this dimension
    managed_vars_env_var = get_managed_vars_env_var(dim_name)
    if newly_managed_vars:
        # Store the list of variables as a JSON string
        # Ensure proper quoting for the JSON string itself
        json_string = json.dumps(newly_managed_vars)
        quoted_json = f"'{json_string.replace("'", "'\\''")}'"
        commands.append(f"export {managed_vars_env_var}={quoted_json}")
    else:
        # If the new profile has no vars, unset the tracker
        commands.append(f"unset {managed_vars_env_var}")

    # 5. Set the active profile marker variable
    active_profile_var = get_active_profile_env_var(dim_name)
    commands.append(f"export {active_profile_var}='{profile_name}'")

    return commands


def generate_deactivate_commands(dimension: Dimension) -> List[str]:
    """
    Generates shell commands to deactivate the current profile for the given dimension.
    Unsets variables based on the MUX_MANAGED_VARS tracker.
    """
    commands = []
    dim_name = dimension.name

    # 1. Get the list of variable names managed by the currently active profile
    currently_managed_vars = get_currently_managed_vars(dim_name)

    # 2. Generate unset commands for all variables managed by the profile being deactivated
    for var_name in currently_managed_vars:
        commands.append(f"unset {var_name}")

    # 3. Unset the managed variables tracker itself
    managed_vars_env_var = get_managed_vars_env_var(dim_name)
    commands.append(f"unset {managed_vars_env_var}")

    # 4. Unset the active profile marker variable
    active_profile_var = get_active_profile_env_var(dim_name)
    commands.append(f"unset {active_profile_var}")

    return commands 