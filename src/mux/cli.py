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
from .ui import print_error, print_success, print_warning, display_show_table
from .__version__ import __version__
from .config import MUX_DIR, DIMS_DIR
from .utils import ensure_mux_dir_exists

# Mux internals
from .dimension import get_dimension_tree, find_dimensions, Dimension
from .state import (
    generate_activate_commands,
    generate_deactivate_commands,
    get_active_profile
)

# Global console objects
console = Console()
console_err = Console(stderr=True)

# --- Helper Functions ---

# --- Command Implementations ---

def handle_status(args):
    """Implements the 'mux status' command."""
    root_dims = get_dimension_tree(DIMS_DIR)
    if not root_dims:
        console.print("[yellow]No dimensions found.[/yellow]")
        return

    # Pass args.verbose to Mux.handle_status method
    mux = Mux()
    mux.handle_status(verbose=args.verbose)

def handle_switch(args):
    """Implements the 'mux switch' command. Prints shell commands."""
    dim_name: Optional[str] = args.dimension
    profile_name: Optional[str] = args.profile
    
    # Initialize Mux
    mux = Mux()
    
    try:
        # Let the core Mux class handle all aspects of switching,
        # including dimension/profile lookup and FZF interaction
        mux.handle_switch(dim_name, profile_name)
    except FzfNotInstalledError as e:
        print_error(str(e))
        print_error("Please install fzf to use interactive selection: https://github.com/junegunn/fzf")
        sys.exit(1)
    except (DimensionNotFoundError, ProfileNotFoundError) as e:
        print_error(str(e))
        sys.exit(1)


def handle_show(args):
    """Implements the 'mux show' command."""
    dim_name: str = args.dimension
    mux = Mux()
    try:
        # Delegate logic to Mux class
        mux.handle_show(dim_name)
    except (DimensionNotFoundError, ProfileNotFoundError) as e:
        print_error(str(e))
        sys.exit(1)


def handle_set_default(args):
    """Implements the 'mux set-default' command."""
    dim_name: Optional[str] = args.dimension
    profile_name: Optional[str] = args.profile
    
    # Initialize Mux instance
    mux = Mux()
    
    try:
        # Let the core Mux class handle all aspects of setting the default,
        # including dimension/profile lookup and FZF interaction
        mux.handle_set_default(dim_name, profile_name)
    except FzfNotInstalledError as e:
        print_error(str(e))
        print_error("Please install fzf to use interactive selection: https://github.com/junegunn/fzf")
        sys.exit(1)
    except (DimensionNotFoundError, ProfileNotFoundError) as e:
        print_error(str(e))
        sys.exit(1)

def handle_hook(args):
    """Generates shell code for the auto-activation hook."""
    # This script defines the hook function and registers it for bash/zsh/fish
    from .prompt_scripts import get_prompt_script
    import sys # Added sys import

    shell = args.shell
    try:
        script = get_prompt_script(shell)
        print(script)
    except ValueError:
        # This should ideally not happen due to argparse choices, but good practice
        console_err.print(f"Error: Unsupported shell '{shell}' provided.", style="bold red")
        sys.exit(1)

def handle_init(args):
    """Implements the 'mux init' command to set up the directory structure."""
    # Create base directories
    ensure_mux_dir_exists()  # This ensures ~/.mux exists
    
    # Create dims and defaults directories if they don't exist
    DIMS_DIR.mkdir(exist_ok=True)
    
    # Report what was created
    console.print(f"[green]✓[/green] Created Mux directory: [bold]{MUX_DIR}[/bold]")
    console.print(f"[green]✓[/green] Created dimensions directory: [bold]{DIMS_DIR}[/bold]")
    
    # Create example dimensions if requested
    if args.with_examples:
        # AWS dimension example
        aws_dir = DIMS_DIR / "aws"
        aws_dir.mkdir(exist_ok=True)
        aws_profiles_dir = aws_dir / "profiles"
        aws_profiles_dir.mkdir(exist_ok=True)
        
        # Create example profiles
        with open(aws_profiles_dir / "personal", "w") as f:
            f.write("AWS_PROFILE=personal\nAWS_REGION=us-west-2\n")
        
        with open(aws_profiles_dir / "work", "w") as f:
            f.write("AWS_PROFILE=work\nAWS_REGION=us-east-1\n")
        
        # Set default profile
        with open(aws_dir / "default.txt", "w") as f:
            f.write("personal\n")
            
        # Kubernetes dimension with subdimensions example
        k8s_dir = DIMS_DIR / "k8s"
        k8s_dir.mkdir(exist_ok=True)
        
        # Create profiles.yaml for k8s
        with open(k8s_dir / "profiles.yaml", "w") as f:
            f.write("""# Kubernetes contexts
dev:
  KUBECONFIG: ~/.kube/dev-config
  KUBE_CONTEXT: dev-context
prod:
  KUBECONFIG: ~/.kube/prod-config
  KUBE_CONTEXT: prod-context
""")
        
        # Set default profile
        with open(k8s_dir / "default.txt", "w") as f:
            f.write("dev\n")
        
        # Create subdimension for namespaces
        k8s_dims_dir = k8s_dir / "dims"
        k8s_dims_dir.mkdir(exist_ok=True)
        
        namespace_dir = k8s_dims_dir / "namespace"
        namespace_dir.mkdir(exist_ok=True)
        
        # Create profiles.yaml for namespace
        with open(namespace_dir / "profiles.yaml", "w") as f:
            f.write("""# Kubernetes namespaces
default:
  KUBE_NAMESPACE: default
app:
  KUBE_NAMESPACE: my-application
system:
  KUBE_NAMESPACE: kube-system
""")
        
        # Set default namespace
        with open(namespace_dir / "default.txt", "w") as f:
            f.write("default\n")
            
        console.print(f"[green]✓[/green] Created example dimensions:")
        console.print(f"  • [bold]aws[/bold] - with profiles: personal, work")
        console.print(f"  • [bold]k8s[/bold] - with profiles: dev, prod")
        console.print(f"  • [bold]k8s/namespace[/bold] - with profiles: default, app, system")
    
    # Print next steps
    console.print("\n[bold]Next steps:[/bold]")
    console.print("1. Add your own dimensions and profiles in [bold]~/.mux/dims/[/bold]")
    console.print("2. Use [bold]mux status[/bold] to see your dimensions and profiles")
    console.print("3. Add shell integration with [bold]eval \"$(mux hook <shell>)\"[/bold]")
    console.print("   Example: Add [bold]eval \"$(mux hook zsh)\"[/bold] to your [bold]~/.zshrc[/bold]")


def handle_internal_auto_update(args):
    """
    Internal command called by the shell hook.
    Determines required state based on CWD and prints activation/deactivation commands.
    This function should primarily print commands to stdout and avoid other output
    unless critical errors occur (which should go to stderr, but sparingly).
    """
    config_filename = ".muxrc" # File containing dimension=profile mappings
    all_commands: List[str] = []
    mux = Mux() # Instantiate Mux once
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
         print_error(f"[mux hook] Error accessing/reading {config_filename} hierarchy: {e}")
         sys.exit(1) # Exit to indicate failure to the hook
    except Exception as e:
        # Catch other potential errors during file parsing
        print_error(f"[mux hook] Error processing configuration {config_path_for_error or 'file'}: {e}")
        sys.exit(1)


    # 3. Get all defined dimensions and current active profiles
    all_defined_dims = mux.all_dimensions
    currently_active_profiles: Dict[str, str] = {}
    for dim_name in all_defined_dims.keys():
        active = get_active_profile(dim_name)
        if active:
            currently_active_profiles[dim_name] = active

    # 4. Determine the set of dimensions to consider (targeted or currently active)
    affected_dim_names = set(target_profiles.keys()) | set(currently_active_profiles.keys())

    # 5. Generate activation/deactivation commands
    for dim_name in affected_dim_names:
        dimension = all_defined_dims.get(dim_name)
        if not dimension:
            # Referenced dimension doesn't exist, skip.
            # If it was active, its state var will just remain.
            # If it was in .muxrc, we can't activate it.
            continue

        target_profile = target_profiles.get(dim_name) # Desired profile from .muxrc (or None)
        current_profile = currently_active_profiles.get(dim_name) # Current active profile from env

        commands_for_dim: List[str] = [] # Collect commands for this dimension
        try:
            if found_config:
                # .muxrc determines the state
                if target_profile:
                    # Target profile specified in .muxrc
                    if current_profile != target_profile:
                        # Need to switch or activate
                        if target_profile in dimension.get_profile_names():
                            commands_for_dim = generate_activate_commands(dimension, target_profile)
                        else:
                            # Target profile doesn't exist, warn and deactivate if needed
                            print_warning(f"[hook] Profile '{target_profile}' in '{config_path_for_error}' not found for dim '{dim_name}'. Deactivating.")
                            if current_profile:
                                commands_for_dim = generate_deactivate_commands(dimension)
                else:
                    # .muxrc exists but doesn't mention this dim. Deactivate if active.
                    if current_profile:
                        commands_for_dim = generate_deactivate_commands(dimension)
            else:
                # No .muxrc found. Maintain the current state based on env vars.
                if current_profile:
                     # Ensure the currently active profile's vars are exported
                     # generate_activate_commands handles deactivation of others if needed within its logic
                    if current_profile in dimension.get_profile_names():
                        commands_for_dim = generate_activate_commands(dimension, current_profile)
                    else:
                        # The active profile recorded in env var doesn't exist anymore!
                        # This is an inconsistent state. Deactivate.
                        print_warning(f"[hook] Active profile '{current_profile}' for dim '{dim_name}' no longer exists. Deactivating.")
                        commands_for_dim = generate_deactivate_commands(dimension)
                # else: No .muxrc and not currently active, do nothing.

            all_commands.extend(commands_for_dim)

        except ProfileNotFoundError as e:
            # Handle case where generate_activate/deactivate fails because profile vanished
            print_warning(f"[hook] Error processing dimension '{dim_name}': {e}. Attempting to deactivate.")
            try:
                # Try to cleanup by deactivating
                if get_active_profile(dim_name): # Check state again before deactivating
                     all_commands.extend(generate_deactivate_commands(dimension))
            except MuxError as deact_e:
                print_error(f"[hook] Failed to deactivate dimension '{dim_name}' after error: {deact_e}")
        except MuxError as e:
            print_error(f"[hook] Error processing dimension '{dim_name}': {e}")
            # Decide if we should attempt deactivation or just report error?
            # For now, just report the error and continue to next dimension.

    # 6. Print the combined commands to stdout
    # Join with semicolons for shell execution
    shell_output = "; ".join(filter(None, all_commands))
    print(shell_output + ";") # Add trailing semicolon


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
    parser_status.add_argument('-v', '--verbose', action='store_true', help='Show all profiles, not just active ones')
    parser_status.set_defaults(func=handle_status)

    # --- mux switch ---
    parser_switch = subparsers.add_parser('switch', 
                                         help='Switch the active profile for a dimension (prints shell commands)',
                                         description='Switch the active profile for a dimension. To execute the changes in your current shell, either:\n'
                                                    '1. Source the shell wrapper using "mux hook <shell>", which provides a mux() function, or\n'
                                                    '2. Manually evaluate the output: eval "$(mux switch dimension profile)"')
    parser_switch.add_argument('dimension', nargs='?', help='Name of the dimension to switch (omit for FZF selector)')
    parser_switch.add_argument('profile', nargs='?', help='Name of the profile to activate (omit for FZF selector)')
    parser_switch.set_defaults(func=handle_switch)

    # --- mux show ---
    parser_show = subparsers.add_parser('show', help='Show environment variables for the active profile of a dimension')
    parser_show.add_argument('dimension', help='Name of the dimension to show')
    parser_show.set_defaults(func=handle_show)

    # --- mux set-default ---
    parser_set_default = subparsers.add_parser('set-default', 
                                           help='Set the default profile for a dimension',
                                           description='Sets the default profile for a dimension. The default profile will be used when switching to the dimension without specifying a profile name.')
    parser_set_default.add_argument('dimension', nargs='?', help='Name of the dimension to set the default for (omit for FZF selector)')
    parser_set_default.add_argument('profile', nargs='?', help='Name of the profile to set as default (omit for FZF selector)')
    parser_set_default.set_defaults(func=handle_set_default)

    # --- mux hook --- 
    parser_hook = subparsers.add_parser('hook', 
                                       help='Generate shell hook script for auto-activation and switch command',
                                       description='Generate shell integration script that does two things:\n'
                                                  '1. Sets up auto-activation when changing directories\n'
                                                  '2. Provides a mux() wrapper function that evaluates the output of "mux switch"\n\n'
                                                  'To use: Add "eval "$(mux hook bash|zsh|fish)"" to your shell init file (~/.bashrc, ~/.zshrc, ~/.config/fish/config.fish)')
    parser_hook.add_argument('shell', choices=['bash', 'zsh', 'fish'], help='Specify the target shell (bash, zsh, fish)')
    parser_hook.set_defaults(func=handle_hook)

    # --- mux init ---
    parser_init = subparsers.add_parser('init',
                                      help='Initialize the Mux directory structure',
                                      description='Creates the necessary directory structure (~/.mux/dims, ~/.mux/defaults) and optionally adds example dimensions')
    parser_init.add_argument('--with-examples', action='store_true', help='Create example dimensions and profiles')
    parser_init.set_defaults(func=handle_init)

    # --- mux _internal_auto_update (Hidden command) ---
    parser_internal_update = subparsers.add_parser('_internal_auto_update') # Hide from help
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
        except Exception as e:
            # Catch unexpected errors during command execution
            # Log the type of error as well for better debugging
            console_err.print(f"[mux {args.command}] Unexpected error: ({type(e).__name__}) {e}")
            sys.exit(1)
    else:
        # No command was provided (and --version/--help wasn't triggered by argparse)
        # This can happen if only 'mux' is typed. Show help.
        parser.print_help()
        sys.exit(1) # Exit with error code because a command is expected

if __name__ == "__main__":
    main()
