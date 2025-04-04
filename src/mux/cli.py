#!/usr/bin/env python3

import argparse
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional

# Rich for pretty printing
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from .core import Mux
from .exceptions import MuxError, FzfNotInstalledError, DimensionNotFoundError, ProfileNotFoundError
from .ui import print_error, print_success, print_warning
from .__version__ import __version__

# Mux internals
from .dimension import Dimension, get_dimension_tree, find_dimensions
from .state import (
    generate_activate_commands,
    generate_deactivate_commands,
    get_profile_var_env_name,
    get_active_profile
)
from .utils import MUX_DIR_PATH, ensure_mux_dir_exists

# Global console objects
console = Console()
console_err = Console(stderr=True, style="bold red") # Console for stderr

# --- Helper Functions ---

def find_dimension(name: str, base_path: Path = MUX_DIR_PATH) -> Optional[Dimension]:
    """Finds a dimension by name within a given base path."""
    # Load dimensions relative to the provided base_path
    all_dims = find_dimensions(base_path)
    return all_dims.get(name) # Simpler lookup


def print_shell_commands(commands: List[str]):
    """Prints shell commands to stdout for the wrapper function to eval."""
    # Ensure newline separation even if list is empty/single
    if commands:
        print("\n".join(commands))

# --- Command Implementations ---

def handle_status(args):
    """Implements the 'mux status' command."""
    root_dims = get_dimension_tree(MUX_DIR_PATH)
    if not root_dims:
        console.print("[yellow]No dimensions found.[/yellow]")
        return

    tree = Tree(
        f"[bold cyan]Mux Status[/bold cyan] ([dim]{MUX_DIR_PATH}[/dim])",
        guide_style="bold bright_blue"
    )

    def add_to_tree(dim: Dimension, parent_node: Tree):
        active_profile = get_active_profile(dim.name) # Use state function
        default_profile = dim.get_default_profile_name()
        
        label = Text(dim.name, style="bold white")
        if active_profile:
            label.append(" -> ")
            label.append(active_profile, style="bold green")
            if active_profile == default_profile:
                label.append(" (default)", style="dim green")
        elif default_profile:
            label.append(f" (default: {default_profile})", style="dim yellow")
        else:
            label.append(" (no active/default)", style="dim red")
            
        node = parent_node.add(label)
        for child in dim.children:
            add_to_tree(child, node)

    for dim in root_dims:
        add_to_tree(dim, tree)
        
    console.print(tree)

def handle_switch(args):
    """Implements the 'mux switch' command. Prints shell commands."""
    dim_name: str = args.dimension
    profile_name: Optional[str] = args.profile
    
    dimension = find_dimension(dim_name, MUX_DIR_PATH)
    if not dimension:
        print_error(f"Dimension '{dim_name}' not found.")
        sys.exit(1)
        
    available_profiles = dimension.get_profile_names()
    if not available_profiles:
         print_error(f"Dimension '{dim_name}' has no profiles defined.")
         sys.exit(1)

    # TODO: Implement FZF integration if profile_name is None
    if profile_name is None:
        print_error("FZF profile selection not yet implemented.")
        print_error("Please provide a profile name: mux switch <dim> <profile>")
        sys.exit(1)

    if profile_name not in available_profiles:
        print_error(f"Profile '{profile_name}' not found for dimension '{dim_name}'.")
        print_error(f"Available profiles: {", ".join(available_profiles)}")
        sys.exit(1)
        
    # Generate and print activation commands
    try:
        commands = generate_activate_commands(dimension, profile_name)
        print_shell_commands(commands)
        # Print success message to stderr so it doesn't interfere with commands
        console_err.print(f"Switched dimension [white]'{dimension.name}'[/white] to profile [green]'{profile_name}'[/green].")
    except MuxError as e:
        print_error(f"Failed to switch: {e}")
        sys.exit(1)


def handle_show(args):
    """Implements the 'mux show' command."""
    dim_name: str = args.dimension
    dimension = find_dimension(dim_name, MUX_DIR_PATH)
    
    if not dimension:
        print_error(f"Dimension '{dim_name}' not found.")
        sys.exit(1)
        
    active_profile = get_active_profile(dimension.name) # Use state function
    if not active_profile:
        console.print(f"No active profile for dimension [bold white]'{dim_name}'[/bold white].")
        return
        
    try:
        env_vars = dimension.get_env_vars(active_profile)
        if not env_vars:
            console.print(f"Active profile [bold green]'{active_profile}'[/bold green] for dimension [bold white]'{dim_name}'[/bold white] has no environment variables defined.")
            return

        table = Table(title=f"Active Environment for [bold white]'{dim_name}'[/bold white] ([bold green]{active_profile}[/bold green])",
                      show_header=True, header_style="bold magenta")
        table.add_column("Variable Name", style="dim cyan", width=30)
        table.add_column("Current Value", style="white") # Show actual current env value
        
        for var_name in env_vars.keys(): # Iterate through expected vars
            # Mux manages the original var name export, not a prefixed one usually
            current_value = os.environ.get(var_name, "[dim i](Not Set)[/dim i]")
            # Highlight if the value is different from what mux *thinks* it should be? Maybe too complex.
            # Let's just show the current value for the var name mux expects to manage.
            table.add_row(var_name, current_value)
        
        console.print(table)
    except ProfileNotFoundError:
         print_error(f"Active profile '{active_profile}' seems to be missing or invalid for dimension '{dim_name}'.")
         sys.exit(1)
    except MuxError as e:
        print_error(f"Error showing environment for '{dim_name}': {e}")
        sys.exit(1)


def handle_default(args):
    """Implements the 'mux default' command."""
    dim_name: str = args.dimension
    profile_name: str = args.profile
    
    dimension = find_dimension(dim_name, MUX_DIR_PATH)
    if not dimension:
        print_error(f"Dimension '{dim_name}' not found.")
        sys.exit(1)
        
    if profile_name not in dimension.get_profile_names():
        print_error(f"Profile '{profile_name}' not found for dimension '{dim_name}'.")
        print_error(f"Available profiles: {", ".join(dimension.get_profile_names())}")
        sys.exit(1)
        
    try:
        if dimension.set_default_profile(profile_name):
            print_success(f"Default profile for dimension '{dimension.name}' set to '{profile_name}'.")
    except MuxError as e:
        print_error(f"Failed to set default profile: {e}")
        sys.exit(1)


def handle_auto(args):
    """Generates shell code for the auto-activation hook."""
    # This script defines the hook function and registers it for bash/zsh
    script = """
_mux_auto_hook() {
  # Check if mux command exists to avoid errors if mux is removed
  if ! command -v mux >/dev/null; then
    # Optional: print a warning to stderr?
    # echo "mux command not found, cannot run auto hook." >&2
    return 1
  fi

  # Call mux internal command to get activation/deactivation commands
  local commands
  # Use command substitution robustly, redirect stderr to avoid hook noise
  if commands=$(mux _internal_auto_update 2>/dev/null); then
      # Check if command substitution succeeded and produced output
      if [[ -n "$commands" ]]; then
          eval "$commands"
      fi
  else
      # Optional: Handle error from _internal_auto_update if needed
      # Mux command failed, potentially print to stderr?
      # echo "Mux auto update failed" >&2
      return 1 # Propagate error status
  fi
}

# Detect shell and register hook
if [[ -n "$ZSH_VERSION" ]]; then
  # Zsh setup using chpwd_functions array
  # Check if the function is already in the array to avoid duplicates
  if [[ ! " ${chpwd_functions[*]} " =~ " _mux_auto_hook " ]]; then
    # Add the function to the array
    chpwd_functions+=(_mux_auto_hook)
  fi
  # Run once immediately to set initial state
  _mux_auto_hook
elif [[ -n "$BASH_VERSION" ]]; then
  # Bash setup using PROMPT_COMMAND string
  _mux_prompt_command_hook() {
    # Prevent infinite loops if something in the hook triggers PROMPT_COMMAND again
    if [[ "$_MUX_IN_PROMPT_COMMAND" != "1" ]]; then
       export _MUX_IN_PROMPT_COMMAND=1
       _mux_auto_hook # Run the actual hook logic
       # Capture exit status of the hook
       local hook_exit_status=$?
       unset _MUX_IN_PROMPT_COMMAND
       # Return the hook's exit status to allow chaining in PROMPT_COMMAND
       return $hook_exit_status
    fi
    return 0 # Avoid running recursively
  }
  # Add our hook wrapper to PROMPT_COMMAND if it's not already there
  # Ensure it's added safely and preserves existing commands
  if [[ ! "$PROMPT_COMMAND" =~ _mux_prompt_command_hook ]]; then
    PROMPT_COMMAND="_mux_prompt_command_hook${PROMPT_COMMAND:+;}${PROMPT_COMMAND}"
  fi
  # Run once immediately to set initial state
  _mux_auto_hook
else
  # Unsupported shell
  echo "[mux auto] Error: Unsupported shell. Only Bash and Zsh are currently supported for auto-activation." >&2
fi

# Optional: Clean up helper function if defined and not needed globally
# unset -f _mux_prompt_command_hook # Might be risky if user has a function with the same name

"""
    print(script)


def handle_internal_auto_update(args):
    """
    Internal command called by the shell hook.
    Determines required state based on CWD and prints activation/deactivation commands.
    This function should primarily print commands to stdout and avoid other output
    unless critical errors occur (which should go to stderr, but sparingly).
    """
    config_filename = ".muxrc" # File containing dimension=profile mappings
    target_profiles: Dict[str, Optional[str]] = {} # Store desired state: dim -> profile (or None to deactivate)
    found_config = False
    config_path_for_error = None # Store path for potential error messages

    # 1. Search upwards for the config file
    try:
        current_dir = Path.cwd()
        config_path = None
        # Optimization: Stop searching at home directory or repo root? For now, search all parents.
        for parent in [current_dir] + list(current_dir.parents):
            potential_path = parent / config_filename
            if potential_path.is_file():
                config_path = potential_path
                config_path_for_error = str(config_path) # Store for error reporting
                found_config = True
                break

        # 2. Parse the config file if found
        if config_path:
            with open(config_path, 'r') as f:
                for line_num, line in enumerate(f, 1): # Add line numbers for errors
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        dim_name, profile_name = line.split('=', 1)
                        dim_name = dim_name.strip()
                        profile_name = profile_name.strip()
                        if dim_name and profile_name:
                             target_profiles[dim_name] = profile_name
                        else:
                             # Log malformed line to stderr? Hook might become noisy.
                             # console_err.print(f"Warning: Skipping malformed line {line_num} in {config_path}")
                             pass # Silently ignore malformed lines for now
                    else:
                         # console_err.print(f"Warning: Skipping invalid line {line_num} in {config_path}")
                         pass # Silently ignore invalid lines

    except OSError as e:
         # Error accessing directories or reading file, likely permission issue.
         # Print to stderr as this might be unexpected.
         console_err.print(f"[mux _internal_auto_update] Error accessing/reading {config_filename} hierarchy: {e}")
         sys.exit(1) # Exit to indicate failure to the hook
    except Exception as e:
        # Catch other potential errors during file parsing
        console_err.print(f"[mux _internal_auto_update] Error processing configuration {config_path_for_error or 'file'}: {e}")
        sys.exit(1)


    # 3. Get all defined dimensions and current active profiles
    all_defined_dims: Dict[str, Dimension] = {}
    try:
        all_defined_dims_map = find_dimensions(MUX_DIR_PATH)
        all_defined_dims = {name: dim for name, dim in all_defined_dims_map.items() if dim}
    except Exception as e:
        # Error reading dimension structure
        console_err.print(f"[mux _internal_auto_update] Error loading Mux dimensions: {e}")
        sys.exit(1)

    currently_active_profiles: Dict[str, str] = {}
    for dim_name in all_defined_dims.keys():
        active = get_active_profile(dim_name)
        if active:
            currently_active_profiles[dim_name] = active

    # 4. Determine the set of dimensions to consider
    #    Includes dimensions in the target config AND currently active dimensions
    affected_dim_names = set(target_profiles.keys()) | set(currently_active_profiles.keys())

    # 5. Generate activation/deactivation commands
    all_commands: List[str] = []
    processed_dims_for_deactivation = set() # Avoid double deactivation if found_config is false

    for dim_name in affected_dim_names:
        dimension = all_defined_dims.get(dim_name)
        if not dimension:
            # Referenced dimension (in config or env) doesn't exist in ~/.mux definition. Skip.
            # Optionally warn? console_err.print(f"Warning: Dimension '{dim_name}' not defined.")
            continue

        target_profile = target_profiles.get(dim_name) # Desired profile from .muxrc (or None if not mentioned)
        current_profile = currently_active_profiles.get(dim_name) # Current active profile from env

        if found_config:
            # We found a .muxrc file somewhere
            if target_profile:
                # .muxrc specifies a profile for this dimension
                if current_profile != target_profile:
                    # Need to switch or activate
                    if target_profile in dimension.get_profile_names():
                        try:
                            all_commands.extend(generate_activate_commands(dimension, target_profile))
                        except MuxError as e:
                            console_err.print(f"[mux] Error activating {dim_name}={target_profile}: {e}")
                            # Should we try to deactivate instead or just fail? Let's just fail activation.
                    else:
                        # Specified profile doesn't exist for the dimension! Deactivate if active.
                        console_err.print(f"[mux] Warning: Profile '{target_profile}' in '{config_path_for_error}' not found for dim '{dim_name}'. Deactivating.")
                        if current_profile: # Only deactivate if it was active
                            try:
                                all_commands.extend(generate_deactivate_commands(dimension))
                            except MuxError as e:
                                console_err.print(f"[mux] Error deactivating {dim_name}: {e}")

                # else: Already the correct profile, do nothing
            else:
                # .muxrc was found, but doesn't mention this dimension. Deactivate if active.
                if current_profile:
                    try:
                        all_commands.extend(generate_deactivate_commands(dimension))
                    except MuxError as e:
                        console_err.print(f"[mux] Error deactivating {dim_name}: {e}")

            processed_dims_for_deactivation.add(dim_name) # Mark as processed

        else:
            # No .muxrc found in the current hierarchy. Deactivate if active and not already processed.
             if current_profile and dim_name not in processed_dims_for_deactivation:
                 try:
                     all_commands.extend(generate_deactivate_commands(dimension))
                 except MuxError as e:
                     console_err.print(f"[mux] Error deactivating {dim_name}: {e}")


    # 6. Print the combined commands to stdout
    # Only print if there are actual commands to execute
    if all_commands:
        print_shell_commands(all_commands)


def main():
    ensure_mux_dir_exists() # Make sure ~/.mux exists
    
    parser = argparse.ArgumentParser(
        description="Multiplex environment profiles across dimensions.",
        prog="mux",
        formatter_class=argparse.RawDescriptionHelpFormatter # Keep formatting in description
    )
    # Add version argument that works without subcommand
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')

    subparsers = parser.add_subparsers(dest="command",
                                       title='Available commands', # Title for subparsers section in help
                                       help='Run `mux <command> -h` for specific command help')
                                       # Removed required=True for flexibility with --version/--help

    # --- mux status ---
    parser_status = subparsers.add_parser('status', help='Show active profiles for all dimensions')
    parser_status.set_defaults(func=handle_status)

    # --- mux switch ---
    parser_switch = subparsers.add_parser('switch', help='Switch the active profile for a dimension (prints shell commands)')
    parser_switch.add_argument('dimension', help='Name of the dimension to switch')
    parser_switch.add_argument('profile', nargs='?', help='Name of the profile to activate (omit for FZF selector - NOT IMPLEMENTED)')
    parser_switch.set_defaults(func=handle_switch)

    # --- mux show ---
    parser_show = subparsers.add_parser('show', help='Show environment variables for the active profile of a dimension')
    parser_show.add_argument('dimension', help='Name of the dimension to show')
    parser_show.set_defaults(func=handle_show)

    # --- mux default ---
    parser_default = subparsers.add_parser('default', help='Set the default profile for a dimension')
    parser_default.add_argument('dimension', help='Name of the dimension')
    parser_default.add_argument('profile', help='Name of the profile to set as default')
    parser_default.set_defaults(func=handle_default)

    # --- mux auto ---
    parser_auto = subparsers.add_parser('auto', help='Generate shell code for auto-activation hook')
    parser_auto.set_defaults(func=handle_auto)

    # --- mux _internal_auto_update (Hidden command) ---
    parser_internal_update = subparsers.add_parser('_internal_auto_update', help=argparse.SUPPRESS) # Hide from help
    parser_internal_update.set_defaults(func=handle_internal_auto_update)


    # --- Argument Parsing and Execution ---
    args = parser.parse_args()

    # Execute the function associated with the command, if one was provided
    if hasattr(args, 'func'):
        try:
            args.func(args)
        except MuxError as e:
             print_error(str(e)) # Use the helper function for consistent formatting
             sys.exit(1)
        # except FzfNotInstalledError as e: # Example of more specific handling
        #     print_error(str(e))
        #     sys.exit(1)
        except Exception as e:
            # Catch unexpected errors during command execution
            # Log the type of error as well for better debugging
            console_err.print(f"[mux {args.command}] Unexpected error: ({type(e).__name__}) {e}")
            # Optional: Add traceback logging for dev/debug modes
            # import traceback
            # console_err.print(traceback.format_exc())
            sys.exit(1)
    else:
        # No command was provided (and --version/--help wasn't triggered by argparse)
        # This can happen if only 'mux' is typed. Show help.
        parser.print_help()
        sys.exit(1) # Exit with error code because a command is expected

if __name__ == "__main__":
    main()
