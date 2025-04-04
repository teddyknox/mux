import os
from typing import Dict, List, Optional, Tuple

# Forward declaration for type hinting
class Dimension:
    pass

# --- Environment Variable Naming ---

def get_active_profile_env_var(dim_name: str) -> str:
    """Returns the environment variable name storing the active profile for a dimension."""
    # Uppercase dimension name for the variable
    return f"MUX_ACTIVE_{dim_name.upper()}"

def get_profile_var_env_name(dim_name: str, var_name: str) -> str:
    """Returns the namespaced environment variable name for a specific profile variable."""
    # Uppercase both names
    return f"MUX_VAR_{dim_name.upper()}_{var_name.upper()}"


# --- Reading State ---

def get_active_profile(dim_name: str) -> Optional[str]:
    """Gets the currently active profile name for a dimension from the environment."""
    return os.environ.get(get_active_profile_env_var(dim_name))

def get_currently_set_vars_for_dim(dim_name: str) -> Dict[str, str]:
    """Finds all currently set MUX_VAR_ environment variables for a given dimension."""
    prefix = f"MUX_VAR_{dim_name.upper()}_"
    vars_dict = {}
    for key, value in os.environ.items():
        if key.startswith(prefix):
            # Extract original var name (needs to preserve case if we want perfect unset)
            # For simplicity now, we assume the original key was uppercased.
            # A more robust solution might store the original keys somewhere,
            # but let's stick to convention for now.
            # original_var_name = key[len(prefix):] # This gets the UPPERCASE name
            vars_dict[key] = value # Store the full MUX_VAR name
    return vars_dict

# --- Modifying State (Generating Shell Commands) ---

def generate_activate_commands(dimension: Dimension, profile_name: str) -> List[str]:
    """
    Generates shell commands to deactivate the current profile (if any)
    and activate the new profile for the given dimension.
    """
    commands = []
    dim_name = dimension.name
    new_env_vars = dimension.get_env_vars(profile_name)

    # 1. Get currently set MUX_VAR_ variables for this dimension
    current_mux_vars = get_currently_set_vars_for_dim(dim_name)

    # 2. Generate unset commands for all *currently set* MUX variables for this dim
    #    This ensures that variables from a previously active profile are cleared.
    for mux_var_name in current_mux_vars.keys():
        commands.append(f"unset {mux_var_name}") # Unset the MUX_VAR_... variable

    # 3. Generate export commands for the *new* profile's variables
    for var_name, var_value in new_env_vars.items():
        mux_var_name = get_profile_var_env_name(dim_name, var_name)
        # Ensure proper quoting for values with spaces or special chars
        # Basic quoting for now, might need refinement for complex cases
        quoted_value = f"'{var_value.replace("'", "'\\''")}'"
        commands.append(f"export {mux_var_name}={quoted_value}")

    # 4. Set the active profile marker variable
    active_profile_var = get_active_profile_env_var(dim_name)
    commands.append(f"export {active_profile_var}='{profile_name}'")

    return commands


def generate_deactivate_commands(dimension: Dimension) -> List[str]:
    """
    Generates shell commands to deactivate the current profile for the given dimension.
    """
    commands = []
    dim_name = dimension.name

    # 1. Get currently set MUX_VAR_ variables for this dimension
    current_mux_vars = get_currently_set_vars_for_dim(dim_name)

    # 2. Generate unset commands for all currently set MUX variables for this dim
    for mux_var_name in current_mux_vars.keys():
        commands.append(f"unset {mux_var_name}")

    # 3. Unset the active profile marker variable
    active_profile_var = get_active_profile_env_var(dim_name)
    commands.append(f"unset {active_profile_var}")

    return commands 