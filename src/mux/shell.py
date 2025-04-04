#!/usr/bin/env python3

import subprocess
import os
from typing import List, Tuple, Dict, Optional

from .config import ENV_VAR_PREFIX
from .exceptions import FzfNotInstalledError
from .state import get_active_profile_env_var # Import helper from state

# Functions related to shell interactions (env vars, fzf, command generation).

def get_active_profile_from_env(dimension: 'Dimension') -> Optional[str]:
    """Reads the active profile for a dimension object *directly* from the environment."""
    # Use the dimension name and state helper to get the correct environment variable
    env_var_name = get_active_profile_env_var(dimension.name)
    return os.environ.get(env_var_name)

def run_fzf(items: List[str], prompt: Optional[str] = None, active_item: Optional[str] = None) -> Optional[str]:
    """Runs fzf to select an item from the list."""
    if not items:
        return None # No items to choose from
        
    fzf_command = ["fzf"]
    if prompt:
        # Use fzf's --prompt option
        fzf_command.extend(["--prompt", f"{prompt}> "])
        
    # Calculate dynamic height based on number of items
    # Add 3 lines for UI elements (header, prompt, border)
    # Min height of 3 rows, max height of 15 rows or 40% of terminal
    item_count = len(items)
    height_value = min(max(item_count + 3, 3), 15)
    
    # If very few items, use exact height; otherwise use percentage
    if item_count < 10:
        height_param = f"{height_value}"
    else:
        height_param = "40%"
    
    # Add options for better TUI experience
    fzf_command.extend(["--height", height_param, "--border", "--layout=reverse"])
    
    # Enable ANSI colors if we need to highlight the active item
    if active_item is not None:
        fzf_command.append("--ansi")
        
        # Create a new list of items with the active one highlighted
        formatted_items = []
        for item in items:
            if item == active_item:
                formatted_items.append(f"\033[1;32m{item} (active)\033[0m")  # Bold green with (active) suffix
            else:
                formatted_items.append(item)
        
        input_str = "\n".join(formatted_items)
    else:
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
            # Success, remove any ANSI color sequences and "(active)" suffix from the selected item
            selected = fzf_proc.stdout.strip()
            # If we selected the active item with formatting, strip it back to the original name
            if active_item is not None and active_item in selected:
                return active_item
            return selected
        elif fzf_proc.returncode == 1: 
            # No match (e.g., user typed something with no results)
            return None
        elif fzf_proc.returncode == 130:
             # User cancelled (Ctrl+C or Esc)
             return None
        else:
             # Other fzf error
             # Consider printing fzf_proc.stderr for debugging
             return None
             
    except FileNotFoundError:
         raise FzfNotInstalledError()
    except Exception as e:
         # Catch unexpected errors during subprocess execution
         # Re-raise as a runtime error or handle appropriately
         # For now, treat as cancellation
         return None

