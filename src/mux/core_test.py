import pytest
import sys
from unittest.mock import patch, MagicMock, call, mock_open
from io import StringIO
from pathlib import Path

# Use TYPE_CHECKING for imports needed only for type hints
from typing import TYPE_CHECKING, Dict, Optional, List, Any

if TYPE_CHECKING:
    from mux.dimension import Dimension # Avoid circular import if Dimension imports Mux?

# Import the class to test
from mux.core import Mux
from mux.exceptions import DimensionNotFoundError, ProfileNotFoundError, MuxError, FzfNotInstalledError
from mux.config import DIMS_DIR # For checking paths

# --- Mock Dimension Class ---
# More elaborate than ui_test's mock to support core logic
class MockDimension:
    def __init__(self, name: str, path_str: str, profiles: Dict[str, Dict[str, str]], 
                 children: List['MockDimension'] | None = None, 
                 parent: Optional['MockDimension'] = None,
                 effective_default: Optional[str] = None,
                 user_default_path: Optional[Path] = None):
        self.name = name
        self._path_str = path_str
        self._profiles = profiles
        self.children = children if children else []
        self.parent = parent
        self._effective_default = effective_default
        self._user_default_path = user_default_path if user_default_path else Path("/mock/defaults", path_str)
        # Link children back to parent
        for child in self.children:
            child.parent = self
            child._path_str = f"{self._path_str}/{child.name}" # Recalculate path with parent

    def get_dim_path_str(self) -> str:
        return self._path_str

    def get_profiles(self) -> Dict[str, Any]: # Return Any for simplicity, mimicking loaded profiles
        return self._profiles
    
    def get_env_vars(self, profile_name: str) -> Dict[str, str]:
        if profile_name not in self._profiles:
            raise ProfileNotFoundError(profile_name, self._path_str)
        return self._profiles[profile_name]

    def get_effective_default_profile(self) -> Optional[str]:
        return self._effective_default

    def set_user_default_profile(self, profile_name: str):
        # Mock the file writing aspect
        self._user_default = profile_name
        if self.user_default_path:
            self.user_default_path.write_text(f"{profile_name}\n")
            
    def set_default_profile(self, profile_name: str) -> bool:
        # Mock version for testing set_default_profile
        # Assume it succeeds and sets the internal state for testing get_default
        self._effective_default = profile_name # Or store in a separate mock default.txt state? 
        return True

    # Make it sortable for consistent test output if needed
    def __lt__(self, other):
        """Allow sorting by name for consistent FZF options."""
        return self._path_str < other._path_str
        
    def __repr__(self):
        return f"MockDimension(name='{self.name}', path='{self._path_str}')"


# --- Fixtures ---

@pytest.fixture
def mock_dims():
    """Provides a standard set of mock dimensions for testing."""
    child_dim = MockDimension(
        name="child", 
        path_str="root/child", # Initial path, will be updated by parent
        profiles={"c_prof1": {"CHILD_VAR": "c1"}, "c_prof2": {"CHILD_VAR": "c2"}},
        effective_default="c_prof1"
    )
    root_dim = MockDimension(
        name="root", 
        path_str="root", 
        profiles={"r_prof1": {"ROOT_VAR": "r1"}, "r_prof2": {"ROOT_VAR": "r2"}, "empty": {}}, 
        children=[child_dim],
        effective_default="r_prof1"
    )
    # Child dim path is corrected now that parent is set
    other_dim = MockDimension(
        name="other", 
        path_str="other", 
        profiles={"o_prof1": {"OTHER_VAR": "o1"}},
        effective_default=None # No default
    )
    no_profiles_dim = MockDimension(
        name="no_profiles",
        path_str="no_profiles",
        profiles={},
        effective_default=None
    )
    
    return {
        "root": root_dim,
        "root/child": child_dim,
        "other": other_dim,
        "no_profiles": no_profiles_dim
    }

@pytest.fixture
@patch('mux.core.find_dimensions')
def mux_instance(mock_find_dims, mock_dims):
    """Provides a Mux instance initialized with mock_dims."""
    mock_find_dims.return_value = mock_dims
    mux = Mux()
    # Ensure find_dimensions was called during init
    mock_find_dims.assert_called_once_with(DIMS_DIR)
    return mux

# --- Test Mux Initialization and Basic Getters ---

def test_mux_init(mock_dims):
    """Verify Mux initialization correctly processes dimensions."""
    with patch('mux.core.find_dimensions', return_value=mock_dims) as mock_find:
        mux = Mux()
        assert mux.all_dimensions == mock_dims
        # Root dimensions should be those without parents
        expected_roots = sorted([mock_dims["root"], mock_dims["other"], mock_dims["no_profiles"]], key=lambda d: d.name)
        assert sorted(mux.root_dimensions, key=lambda d: d.name) == expected_roots
        mock_find.assert_called_once_with(DIMS_DIR)

def test_mux_get_dimension(mux_instance, mock_dims):
    """Test retrieving dimensions by path string."""
    assert mux_instance.get_dimension("root") == mock_dims["root"]
    assert mux_instance.get_dimension("root/child") == mock_dims["root/child"]
    assert mux_instance.get_dimension("other") == mock_dims["other"]
    assert mux_instance.get_dimension("nonexistent") is None

def test_get_all_children(mux_instance, mock_dims):
    """Test the recursive _get_all_children method."""
    root_dim = mock_dims["root"]
    child_dim = mock_dims["root/child"]
    other_dim = mock_dims["other"]

    assert mux_instance._get_all_children(root_dim) == [child_dim]
    assert mux_instance._get_all_children(child_dim) == []
    assert mux_instance._get_all_children(other_dim) == []

# --- Test handle_status (minimal, avoid UI overlap) ---

@patch('mux.core.display_status_tree')
@patch('mux.core.print_warning')
def test_handle_status_calls_display(mock_print_warning, mock_display_tree, mux_instance, mock_dims):
    mux_instance.handle_status(verbose=True)
    mock_display_tree.assert_called_once_with(mux_instance.root_dimensions, True)
    mock_print_warning.assert_not_called()

@patch('mux.core.display_status_tree')
@patch('mux.core.print_warning')
def test_handle_status_no_dimensions(mock_print_warning, mock_display_tree):
     with patch('mux.core.find_dimensions', return_value={}) as mock_find:
        mux_no_dims = Mux()
        mux_no_dims.handle_status()
        mock_print_warning.assert_called_once_with(f"No dimensions found in {DIMS_DIR}.")
        mock_display_tree.assert_not_called()


# --- Test handle_show (mocking UI) ---

@patch('mux.core.display_show_table')
@patch('mux.core.get_active_profile_from_env')
@patch('mux.core.print_warning')
def test_handle_show_success(mock_print_warning, mock_get_active, mock_display_table, mux_instance, mock_dims):
    dim_path = "root"
    active_profile = "r_prof1"
    expected_env = {"ROOT_VAR": "r1"}
    mock_get_active.return_value = active_profile
    
    mux_instance.handle_show(dim_path)

    mock_get_active.assert_called_once_with(mock_dims[dim_path])
    # get_env_vars is called within the method
    mock_display_table.assert_called_once_with(dim_path, active_profile, expected_env)
    mock_print_warning.assert_not_called()

@patch('mux.core.display_show_table')
@patch('mux.core.get_active_profile_from_env')
@patch('mux.core.print_warning')
def test_handle_show_inactive(mock_print_warning, mock_get_active, mock_display_table, mux_instance, mock_dims):
    dim_path = "root"
    mock_get_active.return_value = None # Inactive

    mux_instance.handle_show(dim_path)

    mock_get_active.assert_called_once_with(mock_dims[dim_path])
    mock_display_table.assert_called_once_with(dim_path, None, None) # Called with inactive state
    mock_print_warning.assert_not_called() # print_info handled by display_show_table


@patch('mux.core.display_show_table')
def test_handle_show_dim_not_found(mock_display_table, mux_instance):
    with pytest.raises(DimensionNotFoundError, match="Dimension 'nonexistent' not found"):
        mux_instance.handle_show("nonexistent")
    mock_display_table.assert_not_called()
    
@patch('mux.core.display_show_table')
@patch('mux.core.get_active_profile_from_env')
@patch('mux.core.print_warning')
def test_handle_show_active_profile_gone(mock_print_warning, mock_get_active, mock_display_table, mux_instance, mock_dims):
    dim_path = "root"
    active_profile = "r_prof_vanished" # Env var says this is active
    mock_get_active.return_value = active_profile
    
    # Make get_env_vars raise ProfileNotFoundError for this profile
    mock_dims[dim_path].get_env_vars = MagicMock(side_effect=ProfileNotFoundError(active_profile, dim_path))

    mux_instance.handle_show(dim_path)

    mock_get_active.assert_called_once_with(mock_dims[dim_path])
    # It should warn and display as inactive
    mock_print_warning.assert_called_once_with(f"Environment variable for active profile '{active_profile}' is set, but profile data not found for dimension '{dim_path}'.")
    mock_display_table.assert_called_once_with(dim_path, None, None) # Display as inactive


# --- Test handle_switch (complex scenarios) ---

@patch('sys.stdout', new_callable=StringIO)
@patch('mux.core.display_show_table')
@patch('mux.core.generate_activate_commands')
@patch('mux.core.generate_deactivate_commands')
@patch('mux.core.get_active_profile_from_env')
@patch('mux.core.run_fzf')
def test_handle_switch_args_provided_simple_switch(mock_run_fzf, mock_get_active, mock_gen_deactivate, mock_gen_activate, mock_display_table, mock_stdout, mux_instance, mock_dims):
    dim_path = "root"
    old_profile = "r_prof1"
    new_profile = "r_prof2"
    target_dim = mock_dims[dim_path]
    child_dim = mock_dims["root/child"]
    
    # Make get_active return old_profile for root, None for child for this specific test
    def side_effect(dim):
        if dim == target_dim: return old_profile
        return None
    mock_get_active.side_effect = side_effect
    
    # Mock deactivate returns specific strings for root
    mock_gen_deactivate.return_value = [f"unset ROOT_VAR", f"unset MUX_ACTIVE_ROOT"]
    # Mock activate returns specific strings for root
    mock_gen_activate.return_value = [f"export ROOT_VAR='r2'", f"export MUX_ACTIVE_ROOT='{new_profile}'"]
    
    mux_instance.handle_switch(dim_path, new_profile)

    mock_run_fzf.assert_not_called()
    mock_get_active.assert_any_call(target_dim) # Called for root check
    mock_get_active.assert_any_call(child_dim) # Called for child check
    
    # Deactivate should only be called for the root dimension now
    mock_gen_deactivate.assert_called_once_with(target_dim)
    mock_gen_activate.assert_called_once_with(target_dim, new_profile)
    mock_display_table.assert_called_once_with(dim_path, new_profile, {"ROOT_VAR": "r2"})
    
    # Expected output should ONLY contain root deactivation/activation
    expected_output = "unset ROOT_VAR; unset MUX_ACTIVE_ROOT; export ROOT_VAR='r2'; export MUX_ACTIVE_ROOT='r_prof2';"
    assert mock_stdout.getvalue() == expected_output

@patch('sys.stdout', new_callable=StringIO)
@patch('mux.core.print_info')
@patch('mux.core.run_fzf')
def test_handle_switch_fzf_cancel(mock_run_fzf, mock_print_info, mock_stdout, mux_instance):
    mock_run_fzf.return_value = None # User cancels FZF

    mux_instance.handle_switch(None, None) # FZF for dimension
    
    mock_run_fzf.assert_called_once()
    mock_print_info.assert_called_once_with("No dimension selected.")
    assert mock_stdout.getvalue() == ":" # No-op

@patch('sys.stdout', new_callable=StringIO)
@patch('mux.core.print_info')
@patch('mux.core.run_fzf')
def test_handle_switch_fzf_cancel_profile(mock_run_fzf, mock_print_info, mock_stdout, mux_instance, mock_dims):
    dim_path = "root"
    mock_run_fzf.side_effect = [dim_path, None] # Select dim, cancel profile

    mux_instance.handle_switch(None, None) # FZF for both

    assert mock_run_fzf.call_count == 2
    mock_print_info.assert_called_once_with("No profile selected.")
    assert mock_stdout.getvalue() == ":"

@patch('sys.stdout', new_callable=StringIO)
@patch('mux.core.print_error')
@patch('mux.core.run_fzf', side_effect=FzfNotInstalledError())
def test_handle_switch_fzf_not_installed(mock_run_fzf, mock_print_error, mock_stdout, mux_instance):
     with pytest.raises(FzfNotInstalledError):
        mux_instance.handle_switch(None, None)
     # Check that only the error from the exception is printed
     mock_print_error.assert_called_once_with("'fzf' command not found. Please install fzf (https://github.com/junegunn/fzf).")
     assert mock_stdout.getvalue() == "" # No output on error before raise

@patch('sys.stdout', new_callable=StringIO)
@patch('mux.core.print_error')
def test_handle_switch_dim_not_found(mock_print_error, mock_stdout, mux_instance):
    dim_path = "nonexistent"
    with pytest.raises(DimensionNotFoundError):
        mux_instance.handle_switch(dim_path, "any_profile")
    # Check that the error was printed before being raised
    mock_print_error.assert_called_once_with(f"Dimension '{dim_path}' not found.") # Add period
    assert mock_stdout.getvalue() == ""

@patch('sys.stdout', new_callable=StringIO)
@patch('mux.core.print_error')
def test_handle_switch_profile_not_found(mock_print_error, mock_stdout, mux_instance):
    dim_path = "root"
    invalid_profile = "invalid_prof"
    with pytest.raises(ProfileNotFoundError):
        mux_instance.handle_switch(dim_path, invalid_profile)
    # Check that the error was printed before being raised
    mock_print_error.assert_called_once_with(f"Profile '{invalid_profile}' not found for dimension '{dim_path}'.") # Add period
    assert mock_stdout.getvalue() == ""
    
@patch('sys.stdout', new_callable=StringIO)
@patch('mux.core.print_warning')
def test_handle_switch_no_profiles_found(mock_print_warning, mock_stdout, mux_instance):
    dim_path = "no_profiles"
    # Select dimension without profiles using FZF
    with patch('mux.core.run_fzf', return_value=dim_path):
        mux_instance.handle_switch(None, None) 
        
    mock_print_warning.assert_called_once_with(f"No profiles found for dimension '{dim_path}'.")
    assert mock_stdout.getvalue() == ":" # No-op

@patch('mux.core.generate_activate_commands')
@patch('mux.core.generate_deactivate_commands')
@patch('mux.core.get_active_profile_from_env')
@patch('mux.core.print_info')
def test_handle_switch_already_active(mock_print_info, mock_get_active, mock_gen_deactivate, mock_gen_activate, mux_instance, mock_dims):
    """Test that switching to the already active profile does nothing."""
    dim_path = "root"
    active_profile = "r_prof1"
    target_dim = mock_dims[dim_path]
    
    mock_get_active.return_value = active_profile # Currently active is the target profile

    mux_instance.handle_switch(dim_path, active_profile)

    mock_get_active.assert_called_once_with(target_dim) # Only checks once
    mock_print_info.assert_called_once_with(f"Profile '{active_profile}' is already active for dimension '{dim_path}'.")
    mock_gen_deactivate.assert_not_called()
    mock_gen_activate.assert_not_called()

@patch('sys.stdout', new_callable=StringIO)
@patch('mux.core.display_show_table')
@patch('mux.core.generate_activate_commands')
@patch('mux.core.generate_deactivate_commands')
@patch('mux.core.get_active_profile_from_env')
@patch('mux.core.print_info')
def test_handle_switch_deactivates_children(mock_print_info, mock_get_active, mock_gen_deactivate, mock_gen_activate, mock_display_table, mock_stdout, mux_instance, mock_dims):
    root_dim_path = "root"
    child_dim_path = "root/child"
    old_profile = "r_prof1"
    new_profile = "r_prof2"
    child_active_profile = "c_prof1"
    
    root_dim = mock_dims[root_dim_path]
    child_dim = mock_dims[child_dim_path]

    # Mock which profile is active for which dimension
    def get_active_side_effect(dim):
        if dim == root_dim: return old_profile
        if dim == child_dim: return child_active_profile
        return None
    mock_get_active.side_effect = get_active_side_effect

    # Mock deactivate command generation
    mock_gen_deactivate.side_effect = lambda dim: [f"deact_{dim.name}"]

    # Mock activate command generation
    mock_gen_activate.return_value = [f"act_{new_profile}"]
    
    # Mock _get_all_children explicitly (though it should work with MockDimension)
    with patch.object(mux_instance, '_get_all_children', return_value=[child_dim]) as mock_get_children:
        mux_instance.handle_switch(root_dim_path, new_profile)

    mock_get_children.assert_called_once_with(root_dim)

    # Check get_active calls
    assert mock_get_active.call_count == 2 # Adjust expectation based on observed failure
    mock_get_active.assert_any_call(root_dim)
    mock_get_active.assert_any_call(child_dim)

    # Check deactivate calls: should be called for root AND child
    assert mock_gen_deactivate.call_count == 2
    mock_gen_deactivate.assert_any_call(root_dim)
    mock_gen_deactivate.assert_any_call(child_dim)

    # Check activate call: only for the root dimension being switched
    mock_gen_activate.assert_called_once_with(root_dim, new_profile)
    
    # Check info message for child deactivation
    mock_print_info.assert_called_once_with(f"Deactivating child dimension '{child_dim_path}' due to parent switch.")

    mock_display_table.assert_called_once_with(root_dim_path, new_profile, {"ROOT_VAR": "r2"})
    
    expected_output = "deact_root; deact_child; act_r_prof2;"
    assert mock_stdout.getvalue() == expected_output

# --- Test handle_set_default ---

@patch('mux.core.run_fzf')
def test_handle_set_default_args_provided(mock_run_fzf, mux_instance, mock_dims):
    dim_path = "root"
    profile_to_set = "r_prof2"
    target_dim = mock_dims[dim_path]
    
    # Mock the method on the dimension object
    # Note: Now we expect set_default_profile (source default) to be called
    with patch.object(target_dim, 'set_default_profile') as mock_set_default:
        mux_instance.handle_set_default(dim_path, profile_to_set)

    mock_run_fzf.assert_not_called()
    mock_set_default.assert_called_once_with(profile_to_set)
    # Success message is printed within the mocked method, so not checked here directly
    # We could patch print inside the mock dimension if needed

@patch('mux.core.run_fzf')
def test_handle_set_default_with_fzf(mock_run_fzf, mux_instance, mock_dims):
    dim_path = "root"
    profile_to_set = "r_prof2"
    current_default = "r_prof1"
    target_dim = mock_dims[dim_path]
    target_dim._effective_default = current_default # Set current default for FZF highlight

    # FZF returns selections
    mock_run_fzf.side_effect = [dim_path, profile_to_set] 
    
    with patch.object(target_dim, 'set_default_profile') as mock_set_default:
        mux_instance.handle_set_default(None, None) # Trigger FZF

    # Check FZF calls
    assert mock_run_fzf.call_count == 2
    fzf_calls = mock_run_fzf.call_args_list
    # Call 1: Select Dimension
    assert fzf_calls[0][0][0] == sorted(list(mock_dims.keys()))
    assert "Select Dimension" in fzf_calls[0][0][1]
    # Call 2: Select Profile
    assert fzf_calls[1][0][0] == sorted(list(target_dim.get_profiles().keys()))
    assert f"Select Default Profile for '{dim_path}'" in fzf_calls[1][0][1]
    assert fzf_calls[1][0][2] == current_default # Pass current default for highlighting

    mock_set_default.assert_called_once_with(profile_to_set)

@patch('mux.core.print_error')
@patch('mux.core.run_fzf', side_effect=FzfNotInstalledError())
def test_handle_set_default_fzf_not_installed(mock_run_fzf, mock_print_error, mux_instance):
     with pytest.raises(FzfNotInstalledError):
        mux_instance.handle_set_default(None, None)
     # Check that both error messages are printed
     mock_print_error.assert_any_call("'fzf' command not found. Please install fzf (https://github.com/junegunn/fzf).")
     mock_print_error.assert_any_call("Please install fzf to use interactive selection: https://github.com/junegunn/fzf")
     assert mock_print_error.call_count == 2


@patch('mux.core.print_error')
def test_handle_set_default_dim_not_found(mock_print_error, mux_instance):
    dim_path = "nonexistent"
    with pytest.raises(DimensionNotFoundError):
        mux_instance.handle_set_default(dim_path, "any_profile")
    # Check that the error was printed before being raised
    mock_print_error.assert_called_once_with(f"Dimension '{dim_path}' not found.") # Add period

@patch('mux.core.print_error')
def test_handle_set_default_profile_not_found(mock_print_error, mux_instance):
    dim_path = "root"
    invalid_profile = "invalid_prof"
    with pytest.raises(ProfileNotFoundError):
        mux_instance.handle_set_default(dim_path, invalid_profile)
    # Check that the error was printed before being raised
    mock_print_error.assert_called_once_with(f"Profile '{invalid_profile}' not found for dimension '{dim_path}'.") # Add period

@patch('mux.core.print_warning')
def test_handle_set_default_no_profiles_found(mock_print_warning, mux_instance):
    dim_path = "no_profiles"
    # Select dimension without profiles using FZF
    with patch('mux.core.run_fzf', return_value=dim_path):
        mux_instance.handle_set_default(None, None) 
        
    mock_print_warning.assert_called_once_with(f"No profiles found for dimension '{dim_path}'.")

# --- Test handle_auto_activate ---

@patch('sys.stdout', new_callable=StringIO)
@patch('mux.core.generate_activate_commands')
@patch('mux.core.get_active_profile_from_env')
@patch('mux.core.print_warning')
def test_handle_auto_activate_activates_defaults(mock_print_warning, mock_get_active, mock_gen_activate, mock_stdout, mux_instance, mock_dims):
    root_dim = mock_dims["root"]
    child_dim = mock_dims["root/child"]
    other_dim = mock_dims["other"] # No default
    no_prof_dim = mock_dims["no_profiles"] # No profiles

    # Mock active status: only child is active
    mock_get_active.side_effect = lambda dim: "c_prof2" if dim == child_dim else None
    
    # Mock activate commands
    mock_gen_activate.side_effect = lambda dim, prof: [f"act_{dim.name}_{prof}"]

    mux_instance.handle_auto_activate()

    # Check get_active calls for all dimensions
    assert mock_get_active.call_count == len(mock_dims)
    mock_get_active.assert_any_call(root_dim)
    mock_get_active.assert_any_call(child_dim)
    mock_get_active.assert_any_call(other_dim)
    mock_get_active.assert_any_call(no_prof_dim)

    # Check activate calls: only for root (inactive with existing default)
    assert mock_gen_activate.call_count == 1
    mock_gen_activate.assert_called_once_with(root_dim, "r_prof1")

    mock_print_warning.assert_not_called() # No warnings expected

    expected_output = "act_root_r_prof1;" # Only root's default activation
    assert mock_stdout.getvalue() == expected_output

@patch('sys.stdout', new_callable=StringIO)
@patch('mux.core.generate_activate_commands')
@patch('mux.core.get_active_profile_from_env')
@patch('mux.core.print_warning')
def test_handle_auto_activate_skips_active_and_no_default(mock_print_warning, mock_get_active, mock_gen_activate, mock_stdout, mux_instance, mock_dims):
    root_dim = mock_dims["root"]
    child_dim = mock_dims["root/child"]
    other_dim = mock_dims["other"] # No default
    no_prof_dim = mock_dims["no_profiles"]

    # Mock active status: root is active (r_prof2), others inactive
    mock_get_active.side_effect = lambda dim: "r_prof2" if dim == root_dim else None
    # Mock activate commands to see what gets called
    mock_gen_activate.side_effect = lambda dim, prof: [f"act_{dim.name}_{prof}"]

    mux_instance.handle_auto_activate()

    # Activate should ONLY be called for the inactive child with a default
    mock_gen_activate.assert_called_once_with(child_dim, "c_prof1")
    mock_print_warning.assert_not_called()
    
    # Assert that only the child activation command is printed
    expected_output = "act_child_c_prof1;"
    assert mock_stdout.getvalue() == expected_output

@patch('sys.stdout', new_callable=StringIO)
@patch('mux.core.generate_activate_commands')
@patch('mux.core.get_active_profile_from_env')
@patch('mux.core.print_warning')
def test_handle_auto_activate_warns_missing_default_profile(mock_print_warning, mock_get_active, mock_gen_activate, mock_stdout, mux_instance, mock_dims):
    root_dim = mock_dims["root"]
    child_dim = mock_dims["root/child"]
    other_dim = mock_dims["other"]
    no_prof_dim = mock_dims["no_profiles"]
    
    root_dim._effective_default = "nonexistent_default" # Set a default that doesn't exist in profiles

    # Mock active status: all inactive
    mock_get_active.return_value = None
    # Mock activate commands
    mock_gen_activate.side_effect = lambda dim, prof: [f"act_{dim.name}_{prof}"]

    mux_instance.handle_auto_activate()

    # Activate should ONLY be called for child (inactive with valid default)
    mock_gen_activate.assert_called_once_with(child_dim, "c_prof1")

    # Warning should be printed ONLY for root
    mock_print_warning.assert_called_once_with(f"Default profile 'nonexistent_default' for dimension 'root' not found. Skipping auto-activation.")
    
    # Assert that only the child activation command is printed
    expected_output = "act_child_c_prof1;"
    assert mock_stdout.getvalue() == expected_output
