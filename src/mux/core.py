#!/usr/bin/env python3

import os
import sys
from pathlib import Path
from typing import Optional, List, Tuple, Dict

# Import necessary modules from the package
from .config import DIMS_DIR
from .state import generate_activate_commands, generate_deactivate_commands # Use new state funcs
from .shell import get_active_profile_from_env, run_fzf # Keep fzf
from .dimension import Dimension, find_dimensions, get_dimension_tree # Import from dimension.py
from .ui import display_status_tree, display_show_table, print_warning, print_success, print_info, print_error # Added display_show_table
from .exceptions import DimensionNotFoundError, ProfileNotFoundError, MuxError, FzfNotInstalledError # Added FzfNotInstalledError

class Mux:
    """
    Orchestrates Mux operations by managing dimensions.
    """
    def __init__(self):
        """Initializes Mux by discovering dimensions."""
        # Discover all dimensions and store them in a flat dictionary keyed by path string
        self.all_dimensions: Dict[str, Dimension] = find_dimensions(DIMS_DIR)
        # Determine root dimensions (those without a parent)
        self.root_dimensions: List[Dimension] = [dim for dim in self.all_dimensions.values() if dim.parent is None]

    def get_dimension(self, dim_path_str: str) -> Optional[Dimension]:
        """Finds a dimension by its path string."""
        return self.all_dimensions.get(dim_path_str)

    def handle_status(self, verbose: bool = False):
        """Handles the 'mux status' command."""
        # Logic to gather status and call UI function
        # Example:
        if not self.root_dimensions:
             print_warning(f"No dimensions found in {DIMS_DIR}.")
             return
        display_status_tree(self.root_dimensions, verbose) # Call UI function with verbose flag

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
                env_vars = dim.get_env_vars(active_profile)
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
                # Get the currently active profile for this dimension
                active_profile = get_active_profile_from_env(dim)
                # Pass the active profile to run_fzf for highlighting
                selected_profile = run_fzf(profile_options, f"Select Profile for '{selected_dim_path}'", active_profile)
                if selected_profile is None:
                    print_info("No profile selected.")
                    sys.stdout.write(":")
                    return # User cancelled fzf

            # --- Validate Selected Profile --- 
            if selected_profile not in available_profiles:
                # Should not happen if selected via fzf
                raise ProfileNotFoundError(selected_profile, selected_dim_path)
        
            # --- Generate Deactivation Commands (Old Profile + Children) --- 
            all_commands = []
            old_profile_name = get_active_profile_from_env(dim) # Check currently active for this specific dim
            
            # 1. Deactivate current profile for the dimension being switched (if active)
            if old_profile_name:
                if old_profile_name == selected_profile:
                    print_info(f"Profile '{selected_profile}' is already active for dimension '{selected_dim_path}'.")
                    sys.stdout.write(":")
                    return
                # Generate commands to deactivate the *old* profile
                deactivate_commands = generate_deactivate_commands(dim)
                all_commands.extend(deactivate_commands)
            
            # 2. Deactivate all child dimensions recursively
            children_to_deactivate = self._get_all_children(dim)
            for child_dim in children_to_deactivate:
                if get_active_profile_from_env(child_dim):
                    print_info(f"Deactivating child dimension '{child_dim.get_dim_path_str()}' due to parent switch.")
                    deactivate_commands = generate_deactivate_commands(child_dim)
                    all_commands.extend(deactivate_commands)

            # --- Generate Activation Commands (New Profile) --- 
            try:
                # Generate commands to activate the *new* profile
                activate_commands = generate_activate_commands(dim, selected_profile)
                all_commands.extend(activate_commands)
                new_env = dim.get_env_vars(selected_profile) # Get env for display
            except ProfileNotFoundError:
                # Should not happen due to earlier checks, but handle defensively
                raise MuxError(f"Target profile '{selected_profile}' disappeared for dimension '{selected_dim_path}'? Aborting.")
            except Exception as e:
                raise MuxError(f"Failed to generate activation commands for profile '{selected_profile}' in '{selected_dim_path}': {e}")

            # --- Display Information --- 
            display_show_table(selected_dim_path, selected_profile, new_env)
            
            # --- Print to stdout --- 
            # Filter out empty strings and join with semicolons for shell execution
            shell_output = "; ".join(filter(None, all_commands))
            if shell_output:
                sys.stdout.write(shell_output + ";") # Ensure trailing semicolon
            else:
                sys.stdout.write(":") # No-op if no commands generated
            
        except FzfNotInstalledError as e:
             print_error(str(e))
             # Maybe suggest installation? 
             # Let the error propagate to the CLI layer to handle exit code
             raise e # Re-raise after printing error
        except (DimensionNotFoundError, ProfileNotFoundError) as e:
             # These are expected user errors, print and exit gracefully for CLI
             print_error(str(e))
             raise e # Re-raise after printing error
        # Let other MuxErrors or unexpected Exceptions propagate to main handler

    def handle_set_default(self, dim_path_str: Optional[str], profile_name: Optional[str]):
        """Handles the 'mux set-default' command with optional FZF selection."""
        selected_dim_path = dim_path_str
        selected_profile = profile_name
        
        try:
            # --- Select Dimension (if needed) --- 
            if selected_dim_path is None:
                if not self.all_dimensions:
                    print_warning(f"No dimensions found in {DIMS_DIR}.")
                    return
                dim_options = sorted(list(self.all_dimensions.keys()))
                selected_dim_path = run_fzf(dim_options, "Select Dimension")
                if selected_dim_path is None:
                    print_info("No dimension selected.")
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
                 return
                 
            if selected_profile is None:
                profile_options = sorted(list(available_profiles.keys()))
                # Get the current default profile for this dimension
                default_profile = dim.get_effective_default_profile()
                # Pass the default profile to run_fzf for highlighting
                selected_profile = run_fzf(profile_options, f"Select Default Profile for '{selected_dim_path}'", default_profile)
                if selected_profile is None:
                    print_info("No profile selected.")
                    return # User cancelled fzf

            # --- Validate Selected Profile --- 
            if selected_profile not in available_profiles:
                # Should not happen if selected via fzf
                raise ProfileNotFoundError(selected_profile, selected_dim_path)
        
            # --- Set the Default Profile ---
            # This writes to default.txt in the dimension directory (source default)
            try:
                # Call the method on the Dimension object we already have
                success = dim.set_default_profile(selected_profile)
                if success:
                    # Print success message from core, as dimension method just returns bool
                    print_success(f"Set default profile for dimension '{dim.get_dim_path_str()}' to '{selected_profile}'.")
                # Else: set_default_profile already printed a warning
            except Exception as e:
                print_error(f"Failed to set default profile: {e}")
                raise MuxError(f"Failed to set default profile: {e}")
            
        except FzfNotInstalledError as e:
             print_error(str(e))
             # Suggest installation
             print_error("Please install fzf to use interactive selection: https://github.com/junegunn/fzf")
             raise e # Re-raise after printing error
        except (DimensionNotFoundError, ProfileNotFoundError) as e:
             # These are expected user errors, print and exit gracefully for CLI
             print_error(str(e))
             raise e # Re-raise after printing error

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
                            # Commands is already a list of strings
                            all_commands.extend(generate_activate_commands(dim, default_profile))
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
            # Join with semicolons for shell execution
            shell_output = "; ".join(filter(None, all_commands))
            sys.stdout.write(shell_output + ";")
        # If no commands, print nothing (or maybe ":" no-op? Let's stick with nothing for now)
            
    def _get_all_children(self, dimension: Dimension) -> List[Dimension]:
        """Recursively gets all children (and grandchildren, etc.) of a dimension."""
        children = list(dimension.children)
        for child in dimension.children:
            children.extend(self._get_all_children(child))
        return children
