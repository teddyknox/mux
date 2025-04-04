"""Utility functions and constants for mux."""

from pathlib import Path
import os
import sys

# Define the base path for mux configurations
# Defaults to ~/.mux, but can be overridden by MUX_DIR_PATH env var
_default_mux_dir = Path.home() / ".mux"
MUX_DIR_PATH = Path(os.environ.get("MUX_DIR_PATH", _default_mux_dir))

def ensure_mux_dir_exists():
    """Checks if the MUX directory exists and creates it if not."""
    try:
        MUX_DIR_PATH.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        # Handle potential errors like permission issues
        print(f"Error: Could not create MUX directory at '{MUX_DIR_PATH}': {e}", file=sys.stderr)
        sys.exit(1) # Exit if the base directory cannot be created 