#!/usr/bin/env python3

import os
import sys
import re
from pathlib import Path
from typing import Optional, List, Tuple, Dict

# Import necessary modules from the package
from .config import DIMS_DIR, DEFAULTS_DIR, DEFAULT_FILENAME, MUX_DEFAULT_PROFILES_DIR, MUX_DIR
from .profiles import load_profiles_for_dimension # Example import
from .shell import get_active_profile_from_env, generate_shell_commands, run_fzf # Added run_fzf
from .ui import display_status_tree, display_show_table, print_warning, print_success, print_info, print_error # Added print_error
from .exceptions import DimensionNotFoundError, ProfileNotFoundError, MuxError, FzfNotInstalledError # Added FzfNotInstalledError

# Helper function to create a safe filename from a dimension path string
def _get_user_default_file_path(dim_path_str: str) -> Path:
    """Converts 'path/to/dim' into ~/.multiplex/defaults/path_to_dim."""
    # Replace slashes and potentially other unsafe chars with underscore
    safe_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', dim_path_str)
    return DEFAULTS_DIR / safe_filename

def dimension_path_to_defaults_path(dimension_path: Path) -> Path:
    """Converts 'path/to/dim' into ~/.mux/defaults/path_to_dim.
    Uses the path relative to DIMS_DIR for the filename part.
    """
    # Calculate path relative to the main DIMS_DIR
    try:
        relative_path = dimension_path.relative_to(DIMS_DIR)
    except ValueError:
        # Handle cases where the path might not be under DIMS_DIR (though unlikely in normal use)
        # Fallback to using the full path name parts, joined by underscore
        relative_path = Path("_".join(dimension_path.parts))
        # Optional: Add a warning here if this case is unexpected
        # print_warning(f"Dimension path {dimension_path} not relative to {DIMS_DIR}. Using fallback filename.")

    # Replace slashes and potentially other unsafe chars with underscore in the relative path
    safe_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', relative_path.as_posix())
    return DEFAULTS_DIR / safe_filename

class Dimension:
    """
    Represents a dimension in the mux configuration.
    (Copy or adapt the Dimension class definition here from your script)
    """
    def __init__(self, name: str, path: Path, parent: Optional['Dimension'] = None):
        self.name = name
        self.path = path
        self.parent = parent
        self.children: List[Dimension] = []
        self._profiles_cache: Optional[Dict[str, Dict]] = None
        self._dim_path_str_cache: Optional[str] = None # Cache for dimension path string
        # ... (rest of the Dimension class implementation) ...

    def get_dim_path_str(self) -> str:
        """Returns the full path string for this dimension (e.g., 'root/child')."""
        if self._dim_path_str_cache is None:
            if self.parent:
                self._dim_path_str_cache = f"{self.parent.get_dim_path_str()}/{self.name}"
            else:
                self._dim_path_str_cache = self.name
        return self._dim_path_str_cache

    def get_profiles(self) -> Dict[str, Dict]:
        """Loads and returns profiles for this dimension."""
        if self._profiles_cache is None:
            self._profiles_cache = load_profiles_for_dimension(self.path, self.parent) # Example call
        return self._profiles_cache

    def _read_default_file(self, file_path: Path) -> Optional[str]:
        """Reads the first non-comment, non-empty line from a default file, stripping whitespace."""
        if file_path.is_file():
            try:
                content = file_path.read_text()
                # Return the first non-empty, non-comment line
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith('#'):
                        return line
            except Exception as e:
                print_warning(f"Error reading default file '{file_path}': {e}")
        return None

    def get_source_default_profile(self) -> Optional[str]:
        """Reads the default profile name from default.txt in the dim dir."""
        return self._read_default_file(self.path / DEFAULT_FILENAME)

    def get_user_default_profile(self) -> Optional[str]:
        """Reads the user-set default profile name from ~/.mux/defaults/."""
        defaults_file_path = dimension_path_to_defaults_path(self.path)
        if not defaults_file_path.exists():
            return None
        return self._read_default_file(defaults_file_path)

    def get_effective_default_profile(self) -> Optional[str]:
        """Returns the user default if set, otherwise the source default."""
        user_default = self.get_user_default_profile()
        if user_default:
            return user_default
        return self.get_source_default_profile()
        
    def set_user_default_profile(self, profile_name: str):
        """Sets the user default profile by writing to ~/.mux/defaults/."""
        if profile_name not in self.get_profiles():
            # This check should ideally happen before calling this method
            # but adding defensively.
            from .exceptions import ProfileNotFoundError
            raise ProfileNotFoundError(profile_name, self.get_dim_path_str())
            
        defaults_file_path = dimension_path_to_defaults_path(self.path)
        try:
            # Ensure the defaults directory exists
            defaults_file_path.parent.mkdir(parents=True, exist_ok=True)
            defaults_file_path.write_text(f"{profile_name}\n")
            print_success(f"Set default profile for dimension '{self.get_dim_path_str()}' to '{profile_name}'.")
        except Exception as e:
             # Use a more specific exception if possible
            from .exceptions import MuxError
            raise MuxError(f"Failed to write user default file '{defaults_file_path}': {e}")
            
    def get_profile_env(self, profile_name: str) -> Dict[str, str]:
        """Gets the environment for a specific profile name within this dimension.
        Currently does not merge with parent environment.
        """
        profiles = self.get_profiles() # Loads profiles if not already cached
        if profile_name not in profiles:
            from .exceptions import ProfileNotFoundError # Import locally to avoid circular dependency
            raise ProfileNotFoundError(profile_name, self.get_dim_path_str())

        # Return a copy to prevent modification of the cached version
        return profiles[profile_name].copy()

    # Method called by Mux.handle_default
    # Renamed from set_configured_default_profile for clarity
    def set_configured_default_profile(self, profile_name: str):
        """Internal method called by Mux to set the user default."""
        # We delegate the actual writing and validation to set_user_default_profile
        self.set_user_default_profile(profile_name)

    # ... other Dimension methods ...


class Mux:
    """
    Orchestrates Mux operations by managing dimensions.
    """
    def __init__(self):
        self.root_dimensions: List[Dimension] = []
        self.all_dimensions: Dict[str, Dimension] = {}
        self._discover_dimensions(DIMS_DIR, None)
        self.all_dimensions = self._get_all_dimensions_flat() # Calculate flat dict *after* discovery
        # Initialize console/UI elements if managed here

    def _discover_dimensions(self, current_dir: Path, parent: Optional[Dimension]):
        """Recursively discovers dimensions starting from current_dir.
        Root dimensions are any directory under DIMS_DIR.
        Sub-dimensions must be located within a 'dims/' subdirectory of their parent.
        """
        if not current_dir.is_dir():
            return

        # Determine if we are discovering root dimensions or sub-dimensions
        is_root_discovery = (parent is None and current_dir == DIMS_DIR)

        if is_root_discovery:
            # Discover root dimensions: any directory directly under DIMS_DIR
            for item in sorted(current_dir.iterdir()):
                if item.is_dir():
                    dim = Dimension(item.name, item, None) # Parent is None
                    self.root_dimensions.append(dim)
                    # Now discover sub-dimensions WITHIN this new root dimension's directory
                    self._discover_dimensions(item, dim) # Pass the new dim as parent
        else:
            # Discover sub-dimensions: look ONLY inside a 'dims' directory
            sub_dims_container = current_dir / "dims"
            if sub_dims_container.is_dir():
                 for item in sorted(sub_dims_container.iterdir()):
                    if item.is_dir():
                        # This item is an actual sub-dimension
                        # The parent is the dimension whose directory we are currently in ('current_dir')
                        dim = Dimension(item.name, item, parent) 
                        if parent: # Parent should be the dimension owning the 'dims' dir
                            parent.children.append(dim)
                        # Recursively search within the sub-dimension's directory
                        # looking for ITS 'dims/' dir. Pass the newly created sub-dim as parent.
                        self._discover_dimensions(item, dim)

    def _get_all_dimensions_flat(self) -> Dict[str, Dimension]:
        """Returns a flat dictionary mapping dim_path_str to Dimension object."""
        flat_dims = {}
        
        def add_dimension(dim: Dimension, prefix: str = ""):
            dim_path = prefix + dim.name
            flat_dims[dim_path] = dim
            for child in dim.children:
                add_dimension(child, dim_path + "/")
        
        for dim in self.root_dimensions:
            add_dimension(dim)
            
        return flat_dims

    def get_dimension(self, dim_path_str: str) -> Optional[Dimension]:
        """Finds a dimension by its path string."""
        return self.all_dimensions.get(dim_path_str)

    def handle_status(self):
        """Handles the 'mux status' command."""
        # Logic to gather status and call UI function
        # Example:
        if not self.root_dimensions:
             print_warning(f"No dimensions found in {DIMS_DIR}.")
             return
        display_status_tree(self.root_dimensions) # Call UI function

    def handle_show(self, dim_path_str: str):
        """Handles the 'mux show <dim>' command."""
        dim = self.get_dimension(dim_path_str)
        if not dim:
            # Raise error if dimension not found
            raise DimensionNotFoundError(dim_path_str)
            
        active_profile = get_active_profile_from_env(dim)
        env_vars = None
        if active_profile:
            try:
                # Use the dimension's method to get env vars for the active profile
                env_vars = dim.get_profile_env(active_profile)
            except ProfileNotFoundError:
                 # This case is unlikely if env var is set, but handle defensively
                 print_warning(f"Environment variable for active profile '{active_profile}' is set, but profile data not found for dimension '{dim_path_str}'.")
                 active_profile = None # Treat as inactive
            except Exception as e:
                 print_warning(f"Error loading environment for active profile '{active_profile}' in '{dim_path_str}': {e}")
                 active_profile = None # Treat as inactive

        display_show_table(dim_path_str, active_profile, env_vars)

    def handle_switch(self, dim_path_str: Optional[str], profile_name: Optional[str]):
        """Handles the 'mux switch' command. Prints shell commands."""
        selected_dim_path = dim_path_str
        selected_profile = profile_name
        
        try:
            # --- Select Dimension (if needed) --- 
            if selected_dim_path is None:
                if not self.all_dimensions:
                    print_warning(f"No dimensions found in {DIMS_DIR}.")
                    sys.stdout.write(":") # No-op for eval
                    return
                dim_options = sorted(list(self.all_dimensions.keys()))
                selected_dim_path = run_fzf(dim_options, "Select Dimension")
                if selected_dim_path is None:
                    print_info("No dimension selected.")
                    sys.stdout.write(":")
                    return # User cancelled fzf

            # --- Get Dimension --- 
            dim = self.get_dimension(selected_dim_path)
            if not dim:
                # Should not happen if selected via fzf, but handle defensively
                raise DimensionNotFoundError(selected_dim_path) 
            
            # --- Select Profile (if needed) --- 
            available_profiles = dim.get_profiles() 
            if not available_profiles:
                 print_warning(f"No profiles found for dimension '{selected_dim_path}'.")
                 sys.stdout.write(":") 
                 return
                 
            if selected_profile is None:
                profile_options = sorted(list(available_profiles.keys()))
                # Maybe add current/default markers to fzf list?
                selected_profile = run_fzf(profile_options, f"Select Profile for '{selected_dim_path}'")
                if selected_profile is None:
                    print_info("No profile selected.")
                    sys.stdout.write(":")
                    return # User cancelled fzf

            # --- Validate Selected Profile --- 
            if selected_profile not in available_profiles:
                # Should not happen if selected via fzf
                raise ProfileNotFoundError(selected_profile, selected_dim_path)
        
            # --- Get Old and New Environments --- 
            old_profile_name = get_active_profile_from_env(dim)
            old_env: Optional[Dict[str, str]] = None
            if old_profile_name:
                if old_profile_name == selected_profile:
                    print_info(f"Profile '{selected_profile}' is already active for dimension '{selected_dim_path}'.")
                    sys.stdout.write(":")
                    return
                try:
                    old_env = dim.get_profile_env(old_profile_name)
                except ProfileNotFoundError:
                    print_warning(f"Currently active profile '{old_profile_name}' not found in '{selected_dim_path}'. Unsetting only.")
                    old_env = None
                except Exception as e:
                    print_warning(f"Error loading env for active profile '{old_profile_name}' in '{selected_dim_path}': {e}. Unsetting only.")
                    old_env = None
            
            try:
                new_env = dim.get_profile_env(selected_profile)
            except Exception as e:
                raise MuxError(f"Failed to load env for target profile '{selected_profile}' in '{selected_dim_path}': {e}")

            # --- TODO: Handle Child Dimension Deactivation --- 
            
            # --- Generate Shell Commands --- 
            shell_commands = generate_shell_commands(
                target_dim_path_str=selected_dim_path,
                old_env=old_env, 
                new_env=new_env, 
                new_profile_name=selected_profile
            )
            
            # --- Print to stdout --- 
            sys.stdout.write(shell_commands)
            
        except FzfNotInstalledError as e:
             print_error(str(e))
             # Maybe suggest installation? 
             # Let the error propagate to the CLI layer to handle exit code
             raise e # Re-raise after printing error
        except (DimensionNotFoundError, ProfileNotFoundError) as e:
             # These are expected user errors, print and exit gracefully for CLI
             print_error(str(e))
             # Let the error propagate to the CLI layer to handle exit code
             raise e # Re-raise after printing error
        # Let other MuxErrors or unexpected Exceptions propagate to main handler

    def handle_default(self, dim_path_str: str, profile_name: str):
        """Handles the 'mux default <dim> <profile>' command."""
        from .exceptions import DimensionNotFoundError, ProfileNotFoundError
        
        dim = self.get_dimension(dim_path_str)
        if not dim:
            raise DimensionNotFoundError(f"Dimension '{dim_path_str}' not found")
        
        # Validate profile
        profiles = dim.get_profiles()
        if profile_name not in profiles:
            raise ProfileNotFoundError(profile_name, dim_path_str)
        
        # Set the default profile
        dim.set_configured_default_profile(profile_name)

    def handle_auto_activate(self):
        """Generates shell commands to activate default profiles for inactive dimensions."""
        all_commands = []
        for dim_path_str, dim in sorted(self.all_dimensions.items()):
            # Check if the dimension is already active
            if get_active_profile_from_env(dim) is None:
                # Dimension is inactive, check for a default
                default_profile = dim.get_effective_default_profile()
                if default_profile:
                    try:
                        # Ensure the default profile actually exists before activating
                        if default_profile in dim.get_profiles():
                            new_env = dim.get_profile_env(default_profile)
                            # Generate commands to activate this default
                            # Pass old_env=None as we are activating from an inactive state
                            commands = generate_shell_commands(
                                target_dim_path_str=dim_path_str,
                                old_env=None, 
                                new_env=new_env, 
                                new_profile_name=default_profile
                            )
                            if commands.strip(): # Avoid adding empty strings
                                all_commands.append(commands.strip())
                        else:
                            # Default profile listed but doesn't exist, print warning
                            print_warning(f"Default profile '{default_profile}' for dimension '{dim_path_str}' not found. Skipping auto-activation.")
                    except ProfileNotFoundError:
                         # Should be caught by the 'in dim.get_profiles()' check, but handle defensively
                         print_warning(f"Default profile '{default_profile}' for dimension '{dim_path_str}' caused an error. Skipping auto-activation.")
                    except Exception as e:
                         print_warning(f"Error auto-activating default profile for '{dim_path_str}': {e}")
        
        # Print all activation commands to stdout for shell evaluation
        if all_commands:
            sys.stdout.write("\n".join(all_commands) + "\n")
        # If no commands, print nothing (or maybe ":" no-op? Let's stick with nothing for now)
            

    # ... potentially other helper methods ...

