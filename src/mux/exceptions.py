#!/usr/bin/env python3

# Custom exceptions for the Mux application.

class MuxError(Exception):
    """Base class for Mux specific errors."""
    pass

class DimensionNotFoundError(MuxError):
    """Raised when a specified dimension cannot be found."""
    def __init__(self, dim_path: str):
        self.dim_path = dim_path
        super().__init__(f"Dimension '{dim_path}' not found.")

class ProfileNotFoundError(MuxError):
    """Raised when a specified profile cannot be found for a dimension."""
    def __init__(self, profile_name: str, dim_path: str):
        self.profile_name = profile_name
        self.dim_path = dim_path
        super().__init__(f"Profile '{profile_name}' not found for dimension '{dim_path}'.")

class InvalidConfigError(MuxError):
    """Raised for general configuration errors (e.g., bad YAML/JSON)."""
    def __init__(self, message: str, file_path: str = None):
        self.file_path = file_path
        prefix = f"Invalid configuration in '{file_path}': " if file_path else "Invalid configuration: "
        super().__init__(prefix + message)

class FzfNotInstalledError(MuxError):
    """Raised when the fzf command is required but not found."""
    def __init__(self):
        super().__init__("'fzf' command not found. Please install fzf (https://github.com/junegunn/fzf).")

