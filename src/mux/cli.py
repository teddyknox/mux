#!/usr/bin/env python3

import argparse
import sys
from .core import Mux
from .ui import print_error
# Removed unused import: , print_shell_init_function
from .config import DIMS_DIR, DEFAULTS_DIR # Example import
# from .exceptions import MuxError # Example import

# Import other necessary modules from your package
# from .shell import generate_commands # etc.


# NEW: Define the function to print the shell init code
# This function could also live in ui.py or shell.py
def print_shell_init_function(shell_name: str):
    """Prints the shell function required for mux integration."""
    # Use a standard multi-line string and .format() to avoid f-string escaping issues.
    # Placeholder {0} will be replaced by shell_name.
    # Literal braces and backslashes are used directly.
    init_script_template = '''
# mux shell integration ({0})
mux() {{
  local output
  # Use 'command' to ensure we call the real executable, not the function itself
  # Capture stdout from the real mux command
  output=$(command mux "$@")
  local exit_code=$?

  # Heuristic check: If the command looks like one that modifies the environment
  # (e.g., 'switch') AND it produced output on stdout, evaluate that output.
  # This relies on 'mux' correctly separating shell commands (stdout)
  # from user messages (stderr).
  local command_arg="${{1:-}}" # Get the first argument safely
  case "$command_arg" in
    switch|activate|set) # Add other verbs that modify env if needed
      if [[ -n "$output" ]]; then
        eval "$output"
      fi
      ;;
    *)
      # For other commands (status, show, help, init, etc.), just print
      # any output they might have produced on stdout.
      # Ideally, these commands only print to stderr, so output should be empty.
      if [[ -n "$output" ]]; then
          printf "%s\n" "$output" # Note: Standard backslash for newline here
      fi
      ;;
  esac
  return $exit_code
}}
'''

    # Format the template with the actual shell name
    init_script = init_script_template.format(shell_name)

    # Print directly to stdout, without using Rich, as this is intended for shell sourcing
    print(init_script.strip())


def main():
    '''Main entry point for the Mux CLI.'''
    parser = argparse.ArgumentParser(
        description="mux: Manage and switch between environment profiles across dimensions.",
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=False # Add custom help handler later
    )
    subparsers = parser.add_subparsers(dest="command", title="Commands")

    # --- Define subparsers ---
    # (Copy subparser definitions from your original script here)
    subparsers.add_parser("status", help="Show activated profiles for each dimension.", add_help=False)
    switch_parser = subparsers.add_parser("switch", help="Switch the active profile. Environment changes are applied automatically via shell integration.", add_help=False)
    switch_parser.add_argument("dimension", nargs="?", help="Dimension path (e.g., 'kube' or 'kube/ns'). Uses fzf if omitted.")
    switch_parser.add_argument("profile", nargs="?", help="Profile name to activate. Uses fzf if omitted.")
    show_parser = subparsers.add_parser("show", help="Show env vars for the active profile of a dimension.", add_help=False)
    show_parser.add_argument("dimension", help="Dimension path (e.g., 'kube' or 'kube/ns').")
    default_parser = subparsers.add_parser("default", help="Set the USER default profile for a dimension.", add_help=False)
    default_parser.add_argument("dimension", help="Dimension path (e.g., 'kube' or 'kube/ns').")
    default_parser.add_argument("profile", help="Profile name to set as user default.")
    subparsers.add_parser("help", help="Show this help message.", add_help=False)

    # NEW: Add the init subparser
    init_parser = subparsers.add_parser("init", help="Print shell initialization script.", add_help=False)
    init_parser.add_argument("shell", choices=['bash', 'zsh'], # Add other shells like 'fish' if supported
                             help="The shell to generate the init script for.")


    # --- Argument Parsing ---
    if len(sys.argv) == 1:
        args = parser.parse_args(['help'])
    else:
        try:
            # Consider adding fuzzy matching or better abbreviation handling if desired
            args = parser.parse_args()
        except SystemExit:
             # Default to help on basic parsing errors
             args = argparse.Namespace(command="help")

    # --- Command Dispatch ---
    try:
        # NEW: Handle the init command FIRST, as it doesn't need a Mux instance
        if args.command == "init":
             print_shell_init_function(args.shell)
             sys.exit(0) # Exit cleanly after printing the script

        # Existing command handling requires Mux instance
        mux_instance = Mux() # Initialize your core orchestrator

        if args.command == "status":
            mux_instance.handle_status() # Call the appropriate method
        elif args.command == "switch":
            # IMPORTANT: Ensure this only prints shell commands to stdout
            # All user messages should go to stderr
            mux_instance.handle_switch(args.dimension, args.profile)
        elif args.command == "show":
            mux_instance.handle_show(args.dimension)
        elif args.command == "default":
            mux_instance.handle_default(args.dimension, args.profile)
        elif args.command == "help":
            handle_help(parser) # Use a local help handler or one from Mux/UI
        else:
            # If 'init' was handled above, this handles unknown commands
            handle_help(parser) # Fallback to help

    except Exception as e: # Replace with more specific exceptions later
        print_error(f"An unexpected error occurred: {e}")
        # Consider adding more debug info here if needed, e.g., traceback
        sys.exit(1)

def handle_help(parser: argparse.ArgumentParser):
    """Prints help message, potentially delegating to UI module."""
    # This can be expanded in the ui.py module
    parser.print_help()
    print("\nShell Integration:")
    # print_shell_integration_help() # Removed - Now handled by 'mux init'
    print("  To enable automatic environment updates, add the following")
    print("  to your shell configuration file (.zshrc, .bashrc, etc.):")
    print("    eval \"$(mux init <your_shell_name>)\" # e.g., zsh or bash")
    print("\nConfiguration:")
    # Add config details here or call a function from ui.py
    print(f"  Dimensions are stored in: {DIMS_DIR}")
    print(f"  User defaults are stored in: {DEFAULTS_DIR}")


if __name__ == "__main__":
    main()
