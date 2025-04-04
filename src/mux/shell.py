#!/usr/bin/env python3

import subprocess
import os
import sys
from typing import List, Tuple, Dict, Optional

from .config import ENV_VAR_PREFIX
from .exceptions import FzfNotInstalledError
# from .exceptions import FzfNotInstalledError # Example

# Functions related to shell interactions (env vars, fzf, command generation).

def get_env_var_name(dim_path_tuple: Tuple[str, ...]) -> str:
    """Generates the MUX_ACTIVE_* environment variable name for a dimension path."""
    return f"{ENV_VAR_PREFIX}_{'_'.join(dim_path_tuple).upper()}"

def get_active_profile_from_env(dimension: 'Dimension') -> Optional[str]:
     """Reads the active profile for a dimension object from the environment."""
     # Generate the expected environment variable name
     # Use the dimension's path string directly for now, assuming Dimension has get_dim_path_str
     # A more robust approach might involve ensuring a consistent tuple representation
     if not hasattr(dimension, 'get_dim_path_str'):
         # Fallback or error if the dimension object doesn't have the required method
         # This indicates an issue with how the dimension object is passed or defined
         # For now, return None, but this should be addressed if it occurs.
         # print_warning(f"Dimension object missing 'get_dim_path_str' method.")
         return None 
         
     dim_path_str = dimension.get_dim_path_str()
     # Convert path string like 'a/b' to 'A_B' for the env var suffix
     env_var_suffix = dim_path_str.replace('/', '_').upper()
     env_var_name = f"{ENV_VAR_PREFIX}_{env_var_suffix}"
     
     return os.environ.get(env_var_name)

def run_fzf(items: List[str], prompt: Optional[str] = None) -> Optional[str]:
    """Runs fzf to select an item from the list."""
    if not items:
        return None # No items to choose from
        
    fzf_command = ["fzf"]
    if prompt:
        # Use fzf's --prompt option
        fzf_command.extend(["--prompt", f"{prompt}> "])
        
    # Add options for better TUI experience
    fzf_command.extend(["--height", "40%", "--border", "--layout=reverse"])
    
    input_str = "\n".join(items)
    
    try:
        fzf_proc = subprocess.run(
            fzf_command,
            input=input_str,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, # Capture stderr to check for fzf errors
            text=True,
            check=False # Don't check=True, handle return codes manually
        )

        if fzf_proc.returncode == 0:
            # Success, return selected item
            return fzf_proc.stdout.strip()
        elif fzf_proc.returncode == 1: 
            # No match (e.g., user typed something with no results)
            return None
        elif fzf_proc.returncode == 130:
             # User cancelled (Ctrl+C or Esc)
             return None
        else:
             # Other fzf error
             # Consider printing fzf_proc.stderr for debugging
             # print_warning(f"fzf exited with unexpected code {fzf_proc.returncode}: {fzf_proc.stderr}")
             return None
             
    except FileNotFoundError:
         raise FzfNotInstalledError()
    except Exception as e:
         # Catch unexpected errors during subprocess execution
         # Re-raise as a runtime error or handle appropriately
         # For now, treat as cancellation
         # print_warning(f"Unexpected error running fzf: {e}")
         return None

def generate_shell_commands(
    target_dim_path_str: str, # e.g., "kube/ns"
    old_env: Optional[Dict[str, str]], # Environment of the currently active profile (if any)
    new_env: Dict[str, str], # Environment of the profile being switched TO
    new_profile_name: str # Name of the profile being switched TO
) -> str:
    """
    Generates shell commands to transition from old_env to new_env.
    Calculates variables to unset and export, including the MUX_ACTIVE variable.
    Ensures unsets happen before exports.
    """
    commands = []
    vars_to_export = new_env.copy() # Start with all new vars needing export
    vars_to_unset = set()

    # Calculate MUX_ACTIVE variable name for the target dimension
    mux_active_var_suffix = target_dim_path_str.replace('/', '_').upper()
    mux_active_var_name = f"{ENV_VAR_PREFIX}_{mux_active_var_suffix}"
    vars_to_export[mux_active_var_name] = new_profile_name # Ensure MUX_ACTIVE is set

    if old_env:
        # Find vars present in old but not new
        for key, old_value in old_env.items():
            if key not in new_env or new_env[key] != old_value:
                vars_to_unset.add(key)
                
        # Always add the target MUX_ACTIVE var to unset if switching from an old profile
        vars_to_unset.add(mux_active_var_name)
            
    else:
        # No old environment, nothing specific to unset from the previous profile
        # but we still might need to unset the target MUX_ACTIVE if it somehow exists
        # (e.g., set manually). Check if it exists in the actual environment.
        if os.environ.get(mux_active_var_name) is not None:
             vars_to_unset.add(mux_active_var_name)
             
    # --- Generate Commands --- 
    
    # Prioritize unsetting MUX_ACTIVE variables
    mux_vars_to_unset = {v for v in vars_to_unset if v.startswith(ENV_VAR_PREFIX)}
    other_vars_to_unset = vars_to_unset - mux_vars_to_unset

    # Unset commands
    for var in sorted(list(mux_vars_to_unset)):
        commands.append(f"unset {var};")
    for var in sorted(list(other_vars_to_unset)):
        # Avoid unsetting a variable that will be immediately exported with the same name
        # This prevents unnecessary `unset FOO; export FOO=bar;` churn if only the value changed.
        # If a var is in both vars_to_unset and vars_to_export, it means the value changed,
        # so just exporting it is sufficient.
        if var not in vars_to_export:
            commands.append(f"unset {var};")

    # Export commands (includes the target MUX_ACTIVE variable)
    for key, value in sorted(vars_to_export.items()):
        # Basic shell escaping for the value
        escaped_value = value.replace("'", "'\\''") # More robust escaping for single quotes
        commands.append(f"export {key}='{escaped_value}';")

    return " ".join(commands)

