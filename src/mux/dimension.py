import os
import json
from pathlib import Path
from typing import Dict, List, Optional
from rich.text import Text

from .config import DIMS_DIR, MUX_DIR
from .exceptions import ProfileNotFoundError, MuxError
from .profiles import load_profiles_for_dimension
from .ui import print_warning
from .state import get_active_profile


class Dimension:
    """Represents a configuration dimension."""

    def __init__(self, name: str, path: Path, parent: Optional['Dimension'] = None):
        self.name = name
        self.path = path
        self.parent = parent
        self._dim_path_str_cache: Optional[str] = None # Cache for dimension path string
        self.children: List['Dimension'] = []
        self._profiles: Dict[str, Dict[str, str]] = {}
        self._default_profile_name: Optional[str] = None
        self._profiles_loaded = False
        self._default_loaded = False
        # Only load the default during initialization, not the profiles
        self._load_default()

    def _load_config(self):
        """Loads profiles and default settings for the dimension."""
        self._load_profiles()
        self._load_default()

    def _load_profiles(self, silent: bool = False):
        """Loads profiles using the centralized loader.
        
        Args:
            silent: If True, suppresses informational warnings about loaded sources
        """
        # Skip if already loaded
        if self._profiles_loaded:
            return
            
        loaded_profiles = None
        try:
            # Pass parent profile name if available for dynamic scripts
            parent_profile = self.parent.get_active_profile_name() if self.parent else None
            loaded_profiles = load_profiles_for_dimension(self.path, parent_profile=parent_profile, silent=silent)
        except Exception as e:
            # Catch any unexpected error during profile loading
            print_warning(f"Failed to load profiles for dimension '{self.name}' at '{self.path}': {e}")
            # Ensure self._profiles is initialized even on error
            
        # Ensure self._profiles is a dict, even if loading returned None or error occurred
        self._profiles = loaded_profiles if loaded_profiles is not None else {}
        self._profiles_loaded = True

    def _load_default(self):
        """Loads the default profile name from default.txt."""
        # Skip if already loaded
        if self._default_loaded:
            return
            
        default_file = self.path / "default.txt"
        if default_file.is_file():
            try:
                with open(default_file, 'r') as f:
                    self._default_profile_name = f.read().strip()
                    # Validation of default profile occurs later, when profiles are loaded
            except Exception as e:
                print_warning(f"Could not read default file {default_file}: {e}")
                self._default_profile_name = None
        self._default_loaded = True

    def get_dim_path_str(self) -> str:
        """Returns the full path string for this dimension (e.g., 'root/child')."""
        if self._dim_path_str_cache is None:
            if self.parent:
                self._dim_path_str_cache = f"{self.parent.get_dim_path_str()}/{self.name}"
            else:
                self._dim_path_str_cache = self.name
        return self._dim_path_str_cache

    def get_profiles(self) -> Dict[str, Dict[str, str]]:
        """Returns the loaded profiles."""
        # Ensure profiles are loaded with silent=True since we're just retrieving information
        if not self._profiles:
            self._load_profiles(silent=True)
        return self._profiles.copy() # Return a copy to prevent external modification

    def get_profile_names(self) -> List[str]:
        """Returns a list of available profile names."""
        return list(self.get_profiles().keys())

    def get_default_profile_name(self) -> Optional[str]:
        """Returns the default profile name, if set."""
        return self._default_profile_name

    def get_env_vars(self, profile_name: str) -> Dict[str, str]:
        """Gets environment variables for a specific profile."""
        return self._profiles.get(profile_name, {})

    def set_default_profile(self, profile_name: str) -> bool:
        """Sets the default profile for this dimension by writing to default.txt."""
        # Ensure profiles are loaded if they haven't been already
        # This might happen if set_default is called before get_profiles
        if not self._profiles:
            self._load_profiles() # Don't silence here since this is a user-initiated action
            
        if profile_name not in self._profiles:
            # Use print_error helper function or print directly to stderr
            print_warning(f"Profile '{profile_name}' does not exist for dimension '{self.name}'.")
            # Consider printing available profiles here as well
            available = self.get_profile_names()
            if available:
                print_warning(f"Available profiles: {', '.join(available)}")
            return False

        default_file = self.path / "default.txt"
        try:
            with open(default_file, 'w') as f:
                f.write(profile_name)
            self._default_profile_name = profile_name
            return True
        except Exception as e:
            print_warning(f"Could not write default file {default_file}: {e}")
            return False

    def get_active_profile_name(self) -> Optional[str]:
        """Gets the currently active profile name from the environment state."""
        # Use the imported state function with the dimension name string
        return get_active_profile(self.name)

    def get_effective_default_profile(self) -> Optional[str]:
        """Returns the source default if valid."""
        # Ensure profiles are loaded silently since we're just checking defaults
        if not self._profiles_loaded:
            self._load_profiles(silent=True)
            
        source_default = self.get_default_profile_name() # From default.txt
        if source_default and source_default in self._profiles:
            return source_default
        elif source_default:
             # Warn if source default exists but profile doesn't
             print_warning(f"Default profile '{source_default}' listed in default file not found in loaded profiles for dimension '{self.name}'.")
             # Reset the default profile if it's invalid
             self._default_profile_name = None

        return None # No valid default found


# --- Helper function to discover dimensions ---

def find_dimensions(base_path: Path = DIMS_DIR) -> Dict[str, Dimension]:
    """Discovers dimensions and their hierarchy recursively.
    Returns a flat dictionary mapping full dimension path string to Dimension object.
    """
    dims_by_path: Dict[Path, Dimension] = {}
    dimensions: Dict[str, Dimension] = {}

    # Find all directories within the base path
    for dim_path in base_path.rglob('*'):
        if not dim_path.is_dir() or dim_path.name.startswith('.'):
            continue

        # Skip "dims" directories - we'll handle them later when establishing parent-child relationships
        if dim_path.name == "dims":
            continue

        # Basic validation: check for profile sources or default file
        has_profiles_dir = (dim_path / "profiles").is_dir()
        has_profiles_yaml = (dim_path / "profiles.yaml").is_file()
        has_profiles_py = (dim_path / "profiles.py").is_file()
        has_default = (dim_path / "default.txt").is_file()
        if not (has_profiles_dir or has_profiles_yaml or has_profiles_py or has_default):
            continue # Skip directories that don't look like dimensions

        dims_by_path[dim_path] = Dimension(dim_path.name, dim_path, parent=None)

    # Establish parent-child relationships and build final dict by path string
    for dim_path, dim_obj in dims_by_path.items():
        # Check if this dimension has a "dims" subdirectory with subdimensions
        subdims_dir = dim_path / "dims"
        if subdims_dir.exists() and subdims_dir.is_dir():
            # Find all immediate subdirectories in the "dims" directory
            for subdim_path in subdims_dir.iterdir():
                if not subdim_path.is_dir() or subdim_path.name.startswith('.'):
                    continue
                
                # Basic validation for subdimension
                has_profiles_dir = (subdim_path / "profiles").is_dir()
                has_profiles_yaml = (subdim_path / "profiles.yaml").is_file()
                has_profiles_py = (subdim_path / "profiles.py").is_file()
                has_default = (subdim_path / "default.txt").is_file()
                if not (has_profiles_dir or has_profiles_yaml or has_profiles_py or has_default):
                    continue # Skip directories that don't look like dimensions
                
                # Create subdimension and establish parent-child relationship
                subdim_obj = Dimension(subdim_path.name, subdim_path, parent=dim_obj)
                dim_obj.children.append(subdim_obj)
                dims_by_path[subdim_path] = subdim_obj
        
        # Add to final dimensions dict by path string
        dimensions[dim_obj.get_dim_path_str()] = dim_obj
    
    # Add all subdimensions to the final dictionary
    for dim_path, dim_obj in dims_by_path.items():
        if dim_obj.parent is not None:  # This is a subdimension
            dimensions[dim_obj.get_dim_path_str()] = dim_obj

    return dimensions

def get_dimension_tree(base_path: Path = DIMS_DIR) -> List[Dimension]:
     """Discovers dimensions and returns the root dimensions."""
     all_dims = find_dimensions(base_path)
     root_dims = [dim for dim in all_dims.values() if dim.parent is None]
     return root_dims 