import os
import json
import subprocess
import yaml  # Add yaml import
import sys # Add import
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .utils import MUX_DIR_PATH
from .state import get_active_profile # Import the actual function


class Dimension:
    """Represents a configuration dimension."""

    def __init__(self, name: str, path: Path, parent: Optional['Dimension'] = None):
        self.name = name
        self.path = path
        self.parent = parent
        self.children: List['Dimension'] = []
        self._profiles: Dict[str, Dict[str, str]] = {}
        self._default_profile_name: Optional[str] = None
        self._load_config()

    def _load_config(self):
        """Loads profiles and default settings for the dimension."""
        self._load_profiles()
        self._load_default()

    def _load_profiles(self):
        """Loads profiles from various sources (manual, yaml, dynamic)."""
        # Precedence: dynamic > yaml > manual files
        if (self.path / "profiles.py").exists():
            self._load_dynamic_profiles()
        elif (self.path / "profiles.yaml").exists():
            self._load_yaml_profiles()
        elif (self.path / "profiles").is_dir():
            self._load_manual_profiles()
        # Else: No profiles defined for this dimension explicitly

    def _load_manual_profiles(self):
        """Loads profiles from individual files in the 'profiles' directory."""
        profiles_dir = self.path / "profiles"
        if not profiles_dir.is_dir():
            return

        for profile_file in profiles_dir.iterdir():
            if profile_file.is_file():
                profile_name = profile_file.stem
                # Basic parsing: assume key=value per line, ignore comments/empty lines
                env_vars = {}
                try:
                    with open(profile_file, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                parts = line.split('=', 1)
                                if len(parts) == 2:
                                    env_vars[parts[0].strip()] = parts[1].strip()
                    self._profiles[profile_name] = env_vars
                except Exception as e:
                    print(f"Warning: Could not parse profile file {profile_file}: {e}")


    def _load_yaml_profiles(self):
        """Loads profiles from profiles.yaml."""
        yaml_path = self.path / "profiles.yaml"
        if not yaml_path.is_file():
            self._profiles = {}
            return
        try:
            with open(yaml_path, 'r') as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    # Expecting format: {profile_name: {var: val, ...}, ...}
                    for name, env_vars in data.items():
                        if isinstance(env_vars, dict):
                             self._profiles[name] = {str(k): str(v) for k, v in env_vars.items()}
                        else:
                            # Print warning to stderr
                            print(f"Warning: Invalid format for profile '{name}' in {yaml_path}. Expected a dictionary.", file=sys.stderr)
                else:
                    # Print warning to stderr
                    print(f"Warning: Invalid format in {yaml_path}. Expected a top-level dictionary.", file=sys.stderr)
        except yaml.YAMLError as e:
             # Print warning to stderr
            print(f"Warning: Could not parse YAML file {yaml_path}: {e}", file=sys.stderr)
        except Exception as e:
             # Print warning to stderr
            print(f"Warning: Error reading {yaml_path}: {e}", file=sys.stderr)
        
        # Ensure profiles dict exists even if loading failed partially
        if not hasattr(self, '_profiles'):
             self._profiles = {}

    def _load_dynamic_profiles(self):
        """Loads profiles by executing profiles.py."""
        script_path = self.path / "profiles.py"
        parent_profile_name = self.parent.get_active_profile_name() if self.parent else None
        parent_arg = parent_profile_name if parent_profile_name is not None else ""

        if not script_path.exists():
            # Don't attempt to run if the script doesn't exist
            self._profiles = {}
            return 

        try:
            # Ensure script is executable (optional, but good practice)
            # os.chmod(script_path, os.stat(script_path).st_mode | 0o111)

            # Use sys.executable to ensure using the correct python interpreter
            result = subprocess.run(
                [sys.executable, str(script_path), parent_arg],
                capture_output=True,
                text=True,
                check=True, 
                cwd=self.path 
            )
            try:
                data = json.loads(result.stdout)
                if isinstance(data, dict):
                    for name, env_vars in data.items():
                        if isinstance(env_vars, dict):
                            self._profiles[name] = {str(k): str(v) for k, v in env_vars.items()}
                        else:
                             print(f"Warning: Invalid format for profile '{name}' from {script_path}. Expected a dictionary.", file=sys.stderr)
                else:
                    print(f"Warning: Invalid JSON structure from {script_path}. Expected a top-level dictionary.", file=sys.stderr)

            except json.JSONDecodeError as e:
                print(f"Warning: Could not parse JSON output from {script_path}: {e}", file=sys.stderr)
                print(f"Output was:\n{result.stdout}", file=sys.stderr)
            except Exception as e: 
                 print(f"Warning: Error processing output from {script_path}: {e}", file=sys.stderr)

        except subprocess.CalledProcessError as e:
            # Print warnings to stderr
            print(f"Warning: Error executing {script_path}: {e}", file=sys.stderr)
            print(f"Stderr:\n{e.stderr}", file=sys.stderr)
        except FileNotFoundError:
             # This should ideally not happen if we use sys.executable
             print(f"Warning: Python interpreter '{sys.executable}' not found. Cannot run {script_path}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: An unexpected error occurred while running {script_path}: {e}", file=sys.stderr)
        
        # If any error occurred, ensure profiles are empty
        if not hasattr(self, '_profiles') or not self._profiles:
            self._profiles = {}


    def _load_default(self):
        """Loads the default profile name from default.txt."""
        default_file = self.path / "default.txt"
        if default_file.is_file():
            try:
                with open(default_file, 'r') as f:
                    self._default_profile_name = f.read().strip()
                    # Validate that the default profile actually exists
                    if self._default_profile_name not in self._profiles:
                         print(f"Warning: Default profile '{self._default_profile_name}' listed in {default_file} not found in loaded profiles for dimension '{self.name}'.", file=sys.stderr)
                         self._default_profile_name = None # Reset if invalid
            except Exception as e:
                print(f"Warning: Could not read default file {default_file}: {e}", file=sys.stderr)
                self._default_profile_name = None


    def get_profiles(self) -> Dict[str, Dict[str, str]]:
        """Returns the loaded profiles."""
        return self._profiles.copy() # Return a copy to prevent external modification

    def get_profile_names(self) -> List[str]:
        """Returns a list of available profile names."""
        return list(self._profiles.keys())

    def get_default_profile_name(self) -> Optional[str]:
        """Returns the default profile name, if set."""
        return self._default_profile_name

    def get_env_vars(self, profile_name: str) -> Dict[str, str]:
        """Gets environment variables for a specific profile."""
        return self._profiles.get(profile_name, {})

    def set_default_profile(self, profile_name: str) -> bool:
        """Sets the default profile for this dimension."""
        # Ensure profiles are loaded if they haven't been already
        # This might happen if set_default is called before get_profiles
        if not self._profiles:
            self._load_profiles()
            
        if profile_name not in self._profiles:
            # Use print_error helper function or print directly to stderr
            print(f"Error: Profile '{profile_name}' does not exist for dimension '{self.name}'.", file=sys.stderr)
            # Consider printing available profiles here as well
            available = self.get_profile_names()
            if available:
                print(f"Error: Available profiles: {', '.join(available)}", file=sys.stderr)
            return False

        default_file = self.path / "default.txt"
        try:
            with open(default_file, 'w') as f:
                f.write(profile_name)
            self._default_profile_name = profile_name
            return True
        except Exception as e:
            print(f"Error: Could not write default file {default_file}: {e}", file=sys.stderr)
            return False

    def get_active_profile_name(self) -> Optional[str]:
         """Gets the currently active profile name from the environment state."""
         # Use the imported state function
         return get_active_profile(self.name)


# --- Helper function to discover dimensions ---

def find_dimensions(base_path: Path = MUX_DIR_PATH) -> Dict[str, Dimension]:
    """Discovers dimensions and their hierarchy recursively."""
    dimensions: Dict[str, Dimension] = {}
    
    # Pass 1: Find all potential dimension directories using rglob
    potential_dim_paths = [p for p in base_path.rglob('*') if p.is_dir() and not p.name.startswith('.')]
    
    # Pass 2: Create Dimension objects for each valid path
    # We store them by full path initially to handle potential name clashes
    dims_by_path: Dict[Path, Dimension] = {}
    for dim_path in potential_dim_paths:
        # Basic validation: Does it contain any profile source or default.txt?
        # This helps avoid treating empty intermediate directories as dimensions.
        has_profiles_dir = (dim_path / "profiles").is_dir()
        has_profiles_yaml = (dim_path / "profiles.yaml").is_file()
        has_profiles_py = (dim_path / "profiles.py").is_file()
        has_default = (dim_path / "default.txt").is_file()
        if not (has_profiles_dir or has_profiles_yaml or has_profiles_py or has_default):
             continue # Skip directories that don't look like dimensions
             
        dim_name = dim_path.name
        # Create object without parent link initially
        dims_by_path[dim_path] = Dimension(dim_name, dim_path, parent=None)

    # Pass 3: Establish parent-child relationships and build final dict by name
    for dim_path, dim_obj in dims_by_path.items():
        parent_path = dim_path.parent
        if parent_path in dims_by_path:
            parent_obj = dims_by_path[parent_path]
            dim_obj.parent = parent_obj
            parent_obj.children.append(dim_obj)
        
        # Add to the final dictionary keyed by name
        # Handle potential name clashes if necessary (e.g., by prefixing with parent name?)
        # For now, assume names are unique or last one wins for a given name.
        dimensions[dim_obj.name] = dim_obj
            
    return dimensions

def get_dimension_tree(base_path: Path = MUX_DIR_PATH) -> List[Dimension]:
     """Discovers dimensions and returns the root dimensions."""
     all_dims = find_dimensions(base_path)
     root_dims = [dim for dim in all_dims.values() if dim.parent is None]
     return root_dims 