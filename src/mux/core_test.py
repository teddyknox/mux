# tests/test_core.py
import pytest
import sys
import os
from unittest.mock import patch, MagicMock, call, PropertyMock
from pathlib import Path
from typing import Dict, List

from mux.core import Dimension, Mux
from mux.config import DIMS_DIR, DEFAULTS_DIR, DEFAULT_FILENAME, ENV_VAR_PREFIX
from mux.exceptions import DimensionNotFoundError, ProfileNotFoundError, MuxError, FzfNotInstalledError


class TestDimension:
    @pytest.fixture
    def mock_profiles(self):
        return {
            "dev": {"VAR1": "value1", "VAR2": "value2"},
            "prod": {"VAR1": "prod1", "VAR2": "prod2"}
        }
    
    @pytest.fixture
    def dimension(self, tmp_path):
        dim_path = tmp_path / "test_dim"
        dim_path.mkdir()
        return Dimension("test", dim_path)
    
    @pytest.fixture
    def dimension_with_path(self, tmp_path):
        dim_path = tmp_path / "test_dim"
        dim_path.mkdir()
        # Ensure the mock dimension has the necessary attributes
        dim = Dimension("test_dim", dim_path)
        # Manually set cache as get_dim_path_str relies on parent calls we aren't testing here
        dim._dim_path_str_cache = "test_dim" 
        return dim
    
    @pytest.fixture
    def setup_dirs(self, tmp_path, monkeypatch):
        """Fixture to set up mocked DIMS_DIR and DEFAULTS_DIR."""
        mock_dims_dir = tmp_path / "dims"
        mock_dims_dir.mkdir()
        mock_defaults_dir = tmp_path / "defaults"
        # No need to mkdir defaults, the function should handle it
        monkeypatch.setattr('mux.core.DIMS_DIR', mock_dims_dir)
        monkeypatch.setattr('mux.core.DEFAULTS_DIR', mock_defaults_dir)
        return mock_dims_dir, mock_defaults_dir
    
    def test_dimension_initialization(self, tmp_path):
        # Test basic initialization
        dim_path = tmp_path / "test_dim"
        dim_path.mkdir()
        
        dim = Dimension("test", dim_path)
        
        assert dim.name == "test"
        assert dim.path == dim_path
        assert dim.parent is None
        assert dim.children == []
        assert dim._profiles_cache is None
    
    def test_dimension_initialization_with_parent(self, tmp_path):
        # Test initialization with parent
        parent_path = tmp_path / "parent_dim"
        parent_path.mkdir()
        parent = Dimension("parent", parent_path)
        
        child_path = tmp_path / "child_dim"
        child_path.mkdir()
        child = Dimension("child", child_path, parent)
        
        assert child.parent == parent
    
    @patch('mux.core.load_profiles_for_dimension')
    def test_get_profiles(self, mock_load_profiles, dimension, mock_profiles):
        # Test profile loading and caching
        mock_load_profiles.return_value = mock_profiles
        
        # First call should use load_profiles_for_dimension
        profiles = dimension.get_profiles()
        assert profiles == mock_profiles
        mock_load_profiles.assert_called_once_with(dimension.path, dimension.parent)
        
        # Second call should use cached value
        mock_load_profiles.reset_mock()
        profiles = dimension.get_profiles()
        assert profiles == mock_profiles
        mock_load_profiles.assert_not_called()

    def test_get_dim_path_str_root(self, tmp_path):
        dim_path = tmp_path / "root"
        dim_path.mkdir()
        dim = Dimension("root", dim_path)
        assert dim.get_dim_path_str() == "root"

    def test_get_dim_path_str_nested(self, tmp_path):
        root_path = tmp_path / "root"
        root_path.mkdir()
        child_path = root_path / "child"
        child_path.mkdir()
        root = Dimension("root", root_path)
        child = Dimension("child", child_path, root)
        assert child.get_dim_path_str() == "root/child"
        # Test caching
        child._dim_path_str_cache = None # Clear cache
        assert child.get_dim_path_str() == "root/child"

    # === Tests for Default Profile Logic ===

    def test_get_source_default_profile_success(self, dimension_with_path):
        default_file = dimension_with_path.path / DEFAULT_FILENAME
        default_file.write_text("  prod  \n#comment\nother")
        assert dimension_with_path.get_source_default_profile() == "prod"

    def test_get_source_default_profile_not_found(self, dimension_with_path):
        assert dimension_with_path.get_source_default_profile() is None

    def test_get_source_default_profile_empty(self, dimension_with_path):
        default_file = dimension_with_path.path / DEFAULT_FILENAME
        default_file.write_text("\n #comment only \n")
        assert dimension_with_path.get_source_default_profile() is None

    @patch('mux.core.print_warning')
    def test_get_source_default_profile_read_error(self, mock_print_warning, dimension_with_path):
        default_file = dimension_with_path.path / DEFAULT_FILENAME
        default_file.touch()
        os.chmod(default_file, 0o000) # Make unreadable
        assert dimension_with_path.get_source_default_profile() is None
        mock_print_warning.assert_called_once()
        assert "Error reading default file" in mock_print_warning.call_args[0][0]
        os.chmod(default_file, 0o644) # Cleanup

    @patch('mux.core.dimension_path_to_defaults_path')
    def test_get_user_default_profile_success(self, mock_path_func, dimension, setup_dirs):
        mock_dims_dir, mock_defaults_dir = setup_dirs
        expected_filename = dimension.name
        expected_full_path = mock_defaults_dir / expected_filename
        mock_path_func.return_value = expected_full_path # Tell the patched function what to return

        expected_full_path.parent.mkdir(parents=True, exist_ok=True) 
        expected_full_path.write_text("  dev  ")
        assert dimension.get_user_default_profile() == "dev"
        mock_path_func.assert_called_once_with(dimension.path) # Verify it was called

    @patch('mux.core.dimension_path_to_defaults_path')
    def test_get_user_default_profile_not_found(self, mock_path_func, dimension, setup_dirs):
        mock_dims_dir, mock_defaults_dir = setup_dirs
        expected_filename = dimension.name
        expected_full_path = mock_defaults_dir / expected_filename
        mock_path_func.return_value = expected_full_path

        mock_defaults_dir.mkdir(parents=True, exist_ok=True)
        assert not expected_full_path.exists()
        assert dimension.get_user_default_profile() is None
        mock_path_func.assert_called_once_with(dimension.path)
        
    @patch('mux.core.dimension_path_to_defaults_path')
    def test_get_user_default_profile_complex_path(self, mock_path_func, tmp_path, setup_dirs):
        mock_dims_dir, mock_defaults_dir = setup_dirs
        root_path = mock_dims_dir / "root"
        root_path.mkdir()
        sub_dim_container = root_path / "dims"
        sub_dim_container.mkdir()
        child_path = sub_dim_container / "child.dim"
        child_path.mkdir()
        root = Dimension("root", root_path)
        child = Dimension("child.dim", child_path, root)
        child._dim_path_str_cache = "root/child.dim" # Needed for get_profiles call within set_user_default

        expected_default_filename = "root_child.dim" 
        expected_full_path = mock_defaults_dir / expected_default_filename
        mock_path_func.return_value = expected_full_path

        expected_full_path.parent.mkdir(parents=True, exist_ok=True)
        expected_full_path.write_text("complex_prof")
        
        assert child.get_user_default_profile() == "complex_prof"
        mock_path_func.assert_called_once_with(child.path)

    @patch('mux.core.print_success')
    @patch('mux.core.dimension_path_to_defaults_path')
    def test_set_user_default_profile_success(self, mock_path_func, mock_print_success, dimension, setup_dirs, mock_profiles):
        mock_dims_dir, mock_defaults_dir = setup_dirs
        expected_filename = dimension.name
        expected_full_path = mock_defaults_dir / expected_filename
        mock_path_func.return_value = expected_full_path

        dimension.get_profiles = MagicMock(return_value=mock_profiles)
        
        profile_to_set = "dev"
        dimension.set_user_default_profile(profile_to_set)

        mock_path_func.assert_called_once_with(dimension.path)
        assert mock_defaults_dir.is_dir() 
        assert expected_full_path.is_file()
        assert expected_full_path.read_text() == f"{profile_to_set}\n"
        mock_print_success.assert_called_once()
        assert "Set default profile" in mock_print_success.call_args[0][0]
        assert f"to '{profile_to_set}'" in mock_print_success.call_args[0][0]
        dimension.get_profiles.assert_called_once()

    def test_set_user_default_profile_invalid_profile(self, dimension_with_path, mock_profiles):
        # Mock get_profiles
        dimension_with_path.get_profiles = MagicMock(return_value=mock_profiles)
        
        with pytest.raises(ProfileNotFoundError, match="Profile 'invalid' not found"):
            dimension_with_path.set_user_default_profile("invalid")
            
    @patch('mux.core.Dimension.get_profiles')
    @patch('pathlib.Path.mkdir', side_effect=OSError("Disk full"))
    def test_set_user_default_profile_write_error(self, mock_mkdir, mock_get_profiles, dimension_with_path):
        # Set the return value for the patched get_profiles
        mock_get_profiles.return_value = {"dev": {}, "prod": {}}
        
        with pytest.raises(MuxError, match="Failed to write user default file"):
             dimension_with_path.set_user_default_profile("dev")
        # Check that mkdir was called on the specific DEFAULTS_DIR path object
        # This is a bit indirect, we rely on the side_effect happening
        mock_mkdir.assert_called_once()
        # Optional: Check call args if needed, but knowing it was called is key

    # === Tests for get_profile_env ===

    def test_get_profile_env_success(self, dimension, mock_profiles):
        # Mock get_profiles to return our test profiles
        dimension.get_profiles = MagicMock(return_value=mock_profiles)

        env = dimension.get_profile_env("dev")
        assert env == mock_profiles["dev"]
        # Ensure it's a copy
        assert env is not mock_profiles["dev"]
        dimension.get_profiles.assert_called_once()

    def test_get_profile_env_not_found(self, dimension, mock_profiles):
        # Mock get_profiles
        dimension.get_profiles = MagicMock(return_value=mock_profiles)
        dimension._dim_path_str_cache = "test" # Need path string for error message

        with pytest.raises(ProfileNotFoundError, match="Profile 'nonexistent' not found for dimension 'test'"):
            dimension.get_profile_env("nonexistent")
        dimension.get_profiles.assert_called_once()

    # Test set_configured_default_profile calls set_user_default_profile
    @patch('mux.core.Dimension.set_user_default_profile')
    def test_set_configured_default_profile_calls_set_user(self, mock_set_user, dimension_with_path):
        dimension_with_path.set_configured_default_profile("some_profile")
        mock_set_user.assert_called_once_with("some_profile")

    @patch('mux.core.Dimension.get_user_default_profile')
    @patch('mux.core.Dimension.get_source_default_profile')
    def test_get_effective_default_profile_user_set(
        self, mock_source_default, mock_user_default, dimension_with_path
    ):
        mock_user_default.return_value = "user_choice"
        mock_source_default.return_value = "source_choice"
        assert dimension_with_path.get_effective_default_profile() == "user_choice"
        mock_user_default.assert_called_once()
        mock_source_default.assert_not_called()

    @patch('mux.core.Dimension.get_user_default_profile')
    @patch('mux.core.Dimension.get_source_default_profile')
    def test_get_effective_default_profile_source_set(
        self, mock_source_default, mock_user_default, dimension_with_path
    ):
        mock_user_default.return_value = None
        mock_source_default.return_value = "source_choice"
        assert dimension_with_path.get_effective_default_profile() == "source_choice"
        mock_user_default.assert_called_once()
        mock_source_default.assert_called_once()

    @patch('mux.core.Dimension.get_user_default_profile')
    @patch('mux.core.Dimension.get_source_default_profile')
    def test_get_effective_default_profile_none_set(
        self, mock_source_default, mock_user_default, dimension_with_path
    ):
        mock_user_default.return_value = None
        mock_source_default.return_value = None
        assert dimension_with_path.get_effective_default_profile() is None
        mock_user_default.assert_called_once()
        mock_source_default.assert_called_once()


class TestMux:
    @pytest.fixture
    def mock_dims_dir(self, monkeypatch, tmp_path):
        dims_dir = tmp_path / "dims"
        dims_dir.mkdir()
        monkeypatch.setattr('mux.core.DIMS_DIR', dims_dir)
        # Also mock DEFAULTS_DIR to avoid issues during Mux init if it tries to access it
        defaults_dir = tmp_path / "defaults"
        monkeypatch.setattr('mux.core.DEFAULTS_DIR', defaults_dir)
        return dims_dir
    
    # Test __init__ implicitly tests discovery
    def test_init_and_discover_empty(self, mock_dims_dir):
        # DIRS_DIR is mocked, Mux() will use it for discovery
        mux = Mux()
        assert mux.root_dimensions == []
        assert mux.all_dimensions == {}

    def test_init_and_discover_simple(self, mock_dims_dir):
        # DIRS_DIR is mocked, Mux() will use it
        (mock_dims_dir / "dim1").mkdir()
        (mock_dims_dir / "dim2").mkdir() # No dims/ subdir, so no children
        mux = Mux()
        assert len(mux.root_dimensions) == 2
        assert set(mux.all_dimensions.keys()) == {"dim1", "dim2"}
        dim1 = mux.all_dimensions["dim1"]
        dim2 = mux.all_dimensions["dim2"]
        assert dim1.children == []
        assert dim2.children == []

    def test_init_and_discover_hierarchy(self, mock_dims_dir):
        # Root dimensions
        dim1_path = mock_dims_dir / "dim1"
        dim1_path.mkdir()
        dim2_path = mock_dims_dir / "dim2"
        dim2_path.mkdir()

        # Sub-dimension (must be in dims/)
        dim2_sub_container = dim2_path / "dims"
        dim2_sub_container.mkdir()
        child_path = dim2_sub_container / "child"
        child_path.mkdir()
        ignored_sub_dir_path = dim2_sub_container / "ignored_sub_dir" # This should be discovered
        ignored_sub_dir_path.mkdir() # Re-add mkdir for this directory

        child_sub_container = child_path / "dims"
        child_sub_container.mkdir()
        grandchild_path = child_sub_container / "grandchild"
        grandchild_path.mkdir()
        
        # Files/dirs to ignore
        (dim1_path / "some_file.txt").touch()
        (dim1_path / "profiles").mkdir() # Ignored dir
        (dim2_path / "profiles").mkdir() # Ignored dir
        (child_path / "another_file").touch()

        mux = Mux() # Initialize Mux to trigger discovery using mock_dims_dir

        assert len(mux.root_dimensions) == 2
        dim1 = next(d for d in mux.root_dimensions if d.name == "dim1")
        dim2 = next(d for d in mux.root_dimensions if d.name == "dim2")

        assert dim1.children == [] # dim1 has no dims/ subdir

        assert len(dim2.children) == 2 
        child_names = {c.name for c in dim2.children}
        assert child_names == {"child", "ignored_sub_dir"}

        # Check 'child' hierarchy specifically
        child = next(c for c in dim2.children if c.name == "child")
        assert child.path == child_path
        assert child.parent == dim2
        assert len(child.children) == 1
        grandchild = child.children[0]
        assert grandchild.name == "grandchild"
        assert grandchild.path == grandchild_path
        assert grandchild.parent == child
        assert grandchild.children == []
        
        # Check 'ignored_sub_dir' hierarchy
        ignored_sub_dim = next(c for c in dim2.children if c.name == "ignored_sub_dir")
        assert ignored_sub_dim.path == ignored_sub_dir_path
        assert ignored_sub_dim.parent == dim2
        assert ignored_sub_dim.children == [] # It has no dims/ subdir

        expected_keys = {"dim1", "dim2", "dim2/child", "dim2/ignored_sub_dir", "dim2/child/grandchild"}
        assert set(mux.all_dimensions.keys()) == expected_keys
        assert mux.all_dimensions["dim2/child/grandchild"] == grandchild

    # --- Tests using mocked Mux instance (no filesystem discovery) ---
    @pytest.fixture
    def mocked_mux_instance(self):
        # Patch discovery during fixture creation 
        with patch('mux.core.Mux._discover_dimensions') as mock_discover:
            mux = Mux()
            # Ensure initialization attributes exist even with patched discovery
            mux.root_dimensions = []
            mux.all_dimensions = {}
            return mux

    def test_get_dimension(self, mocked_mux_instance):
        mock_dim = MagicMock()
        mocked_mux_instance.all_dimensions = {"test/path": mock_dim}
        result = mocked_mux_instance.get_dimension("test/path")
        assert result == mock_dim
        assert mocked_mux_instance.get_dimension("nonexistent") is None
    
    @patch('mux.core.print_warning')
    @patch('mux.core.display_status_tree')
    def test_handle_status_empty(self, mock_display, mock_warning, mocked_mux_instance):
        mocked_mux_instance.root_dimensions = []
        mocked_mux_instance.handle_status()
        mock_warning.assert_called_once()
        mock_display.assert_not_called()
    
    @patch('mux.core.print_warning')
    @patch('mux.core.display_status_tree')
    def test_handle_status(self, mock_display, mock_warning, mocked_mux_instance):
        mock_dims = [MagicMock(), MagicMock()]
        mocked_mux_instance.root_dimensions = mock_dims
        mocked_mux_instance.handle_status()
        mock_warning.assert_not_called()
        mock_display.assert_called_once_with(mock_dims)
    
    @patch('mux.core.display_show_table')
    @patch.dict(os.environ, {}, clear=True)
    def test_handle_show(self, mock_display, mocked_mux_instance):
        # Test handling show for an *active* dimension
        dim_path_str = "test/dim"
        profile_name = "active_profile"
        env_vars = {"VAR1": "val1"}
        mux_active_var = f"{ENV_VAR_PREFIX}_TEST_DIM" # Based on get_active_profile_from_env logic
        os.environ[mux_active_var] = profile_name
        
        # Setup mock dimension
        mock_dim = MagicMock(spec=Dimension)
        mock_dim.get_dim_path_str.return_value = dim_path_str
        mock_dim.get_profile_env.return_value = env_vars
        mocked_mux_instance.all_dimensions = {dim_path_str: mock_dim}

        mocked_mux_instance.handle_show(dim_path_str)

        # Verify get_profile_env was called with the active profile name from env
        mock_dim.get_profile_env.assert_called_once_with(profile_name)
        # Verify display is called with the correct args
        mock_display.assert_called_once_with(dim_path_str, profile_name, env_vars)

    @patch('mux.core.display_show_table')
    @patch.dict(os.environ, {}, clear=True)
    def test_handle_show_inactive(self, mock_display, mocked_mux_instance):
        # Test handling show for an *inactive* dimension
        dim_path_str = "test/dim"
        mux_active_var = f"{ENV_VAR_PREFIX}_TEST_DIM"
        if mux_active_var in os.environ:
            del os.environ[mux_active_var]

        mock_dim = MagicMock(spec=Dimension)
        mock_dim.get_dim_path_str.return_value = dim_path_str
        mocked_mux_instance.all_dimensions = {dim_path_str: mock_dim}

        mocked_mux_instance.handle_show(dim_path_str)

        # Verify get_profile_env was NOT called
        mock_dim.get_profile_env.assert_not_called()
        # Verify display is called indicating inactive
        mock_display.assert_called_once_with(dim_path_str, None, None)

    @patch('mux.core.display_show_table')
    def test_handle_show_dimension_not_found(self, mock_display, mocked_mux_instance):
        # Test handling show for non-existent dimension (no change needed here)
        mocked_mux_instance.all_dimensions = {}
        with pytest.raises(DimensionNotFoundError, match="Dimension 'nonexistent' not found"):
            mocked_mux_instance.handle_show("nonexistent")
        mock_display.assert_not_called()
    
    @patch('sys.stdout', new_callable=MagicMock)
    @patch.dict(os.environ, {}, clear=True)
    def test_handle_switch(self, mock_stdout, mocked_mux_instance):
        # Test switching profiles from none active
        dim_path_str = "test/dim"
        new_profile_name = "dev"
        new_env = {"VAR1": "val1", "VAR2": "val2"}
        mux_active_var = f"{ENV_VAR_PREFIX}_TEST_DIM"
        
        # Setup mock dimension
        mock_dim = MagicMock(spec=Dimension)
        mock_dim.get_dim_path_str.return_value = dim_path_str
        mock_dim.get_profiles.return_value = {"dev": {}, "prod": {}} # Need available profiles
        mock_dim.get_profile_env.return_value = new_env
        mocked_mux_instance.all_dimensions = {dim_path_str: mock_dim}
        
        mocked_mux_instance.handle_switch(dim_path_str, new_profile_name)

        # Verify get_profile_env was called for the new profile
        mock_dim.get_profile_env.assert_called_once_with(new_profile_name)
        # Check stdout contains expected commands (generated by real generate_shell_commands)
        output = mock_stdout.write.call_args[0][0]
        assert f"export {mux_active_var}='{new_profile_name}';" in output
        assert "export VAR1='val1';" in output
        assert "export VAR2='val2';" in output
        assert "unset" not in output # Should be no unsets when switching from none

    @patch('sys.stdout', new_callable=MagicMock)
    @patch.dict(os.environ, {}, clear=True)
    def test_handle_switch_change_profile(self, mock_stdout, mocked_mux_instance):
        # Test switching from one active profile to another
        dim_path_str = "test/dim"
        old_profile_name = "prod"
        new_profile_name = "dev"
        old_env = {"VAR_OLD": "p_val", "COMMON": "same"}
        new_env = {"VAR_NEW": "d_val", "COMMON": "same"}
        mux_active_var = f"{ENV_VAR_PREFIX}_TEST_DIM"
        os.environ[mux_active_var] = old_profile_name
        
        mock_dim = MagicMock(spec=Dimension)
        mock_dim.get_dim_path_str.return_value = dim_path_str
        mock_dim.get_profiles.return_value = {"dev": {}, "prod": {}} 
        # Make get_profile_env return different dicts based on profile name
        mock_dim.get_profile_env.side_effect = lambda name: old_env if name == old_profile_name else new_env if name == new_profile_name else {}
        mocked_mux_instance.all_dimensions = {dim_path_str: mock_dim}
        
        mocked_mux_instance.handle_switch(dim_path_str, new_profile_name)
        
        # Verify get_profile_env called for old and new
        mock_dim.get_profile_env.assert_has_calls([
            call(old_profile_name), call(new_profile_name)
        ], any_order=True)
        # Check stdout for expected commands
        output = mock_stdout.write.call_args[0][0]
        assert f"unset {mux_active_var};" in output
        assert "unset VAR_OLD;" in output
        assert "unset COMMON;" not in output # Value is same, should only export
        assert f"export {mux_active_var}='{new_profile_name}';" in output
        assert "export VAR_NEW='d_val';" in output
        assert "export COMMON='same';" in output # Should re-export common var
        assert output.find("unset") < output.find("export") # Unsets before exports
        
    @patch('sys.stdout', new_callable=MagicMock)
    @patch.dict(os.environ, {}, clear=True)
    def test_handle_switch_to_already_active(self, mock_stdout, mocked_mux_instance):
        # Test switching to the profile that is already active
        dim_path_str = "test/dim"
        profile_name = "dev"
        mux_active_var = f"{ENV_VAR_PREFIX}_TEST_DIM"
        os.environ[mux_active_var] = profile_name
        
        mock_dim = MagicMock(spec=Dimension)
        mock_dim.get_dim_path_str.return_value = dim_path_str
        mock_dim.get_profiles.return_value = {"dev": {}, "prod": {}} 
        mocked_mux_instance.all_dimensions = {dim_path_str: mock_dim}

        # Patch the print method of the console_err object in the ui module
        with patch('mux.ui.console_err.print') as mock_console_print:
            mocked_mux_instance.handle_switch(dim_path_str, profile_name)
            
            # Verify console_err.print was called
            mock_console_print.assert_called_once()
            # Check the content of the first argument passed
            call_args, _ = mock_console_print.call_args
            assert "already active" in call_args[0]
            
            # Verify get_profile_env was NOT called
            mock_dim.get_profile_env.assert_not_called()
            # Verify stdout got the no-op command
            mock_stdout.write.assert_called_once_with(":")

    @patch.dict(os.environ, {}, clear=True)
    def test_handle_switch_profile_not_found(self, mocked_mux_instance): # Removed mock_generate
        # Test switching to non-existent profile (no change needed here)
        dim_path_str = "test/dim"
        mock_dim = MagicMock(spec=Dimension)
        mock_dim.get_dim_path_str.return_value = dim_path_str
        mock_dim.get_profiles.return_value = {"dev": {}, "prod": {}}
        mocked_mux_instance.all_dimensions = {dim_path_str: mock_dim}
        
        with pytest.raises(ProfileNotFoundError, match="Profile 'nonexistent' not found for dimension 'test/dim'"):
            mocked_mux_instance.handle_switch(dim_path_str, "nonexistent")
        
        mock_dim.get_profiles.assert_called_once()
        mock_dim.get_profile_env.assert_not_called()

    @patch('mux.core.run_fzf')
    @patch('sys.stdout', new_callable=MagicMock)
    def test_handle_switch_interactive_dim_only(self, mock_stdout, mock_run_fzf, mocked_mux_instance):
        # Test interactive mode (dimension only specified)
        dim_path_str = "test/dim"
        mock_dim = MagicMock(spec=Dimension)
        mock_dim.get_profiles.return_value = {"prof1": {}, "prof2": {}}
        mocked_mux_instance.all_dimensions = {dim_path_str: mock_dim}
        
        # Simulate fzf selecting "prof2"
        mock_run_fzf.return_value = "prof2"
        # Simulate get_profile_env returning something for the chosen profile
        mock_dim.get_profile_env.return_value = {"SELECTED": "prof2_val"}
        
        mocked_mux_instance.handle_switch(dim_path_str, None) # Profile is None
        
        # Check fzf was called for profiles
        mock_run_fzf.assert_called_once_with(sorted(["prof1", "prof2"]), f"Select Profile for '{dim_path_str}'")
        # Check get_profile_env was called for the selected profile
        mock_dim.get_profile_env.assert_called_once_with("prof2")
        # Check stdout contains the export for the selected profile
        output = mock_stdout.write.call_args[0][0]
        assert "export SELECTED='prof2_val';" in output
        assert f"export {ENV_VAR_PREFIX}_TEST_DIM='prof2';" in output # Check MUX_ACTIVE var

    @patch('mux.core.run_fzf')
    @patch('sys.stdout', new_callable=MagicMock)
    def test_handle_switch_interactive_no_args(self, mock_stdout, mock_run_fzf, mocked_mux_instance):
        # Test interactive mode (no arguments specified)
        dim_path_str1 = "dim1"
        dim_path_str2 = "kube/ns"
        mock_dim1 = MagicMock(spec=Dimension)
        mock_dim1.get_profiles.return_value = {"d1p1": {}}
        mock_dim2 = MagicMock(spec=Dimension)
        mock_dim2.get_profiles.return_value = {"k1": {}, "k2": {}}
        mocked_mux_instance.all_dimensions = {dim_path_str1: mock_dim1, dim_path_str2: mock_dim2}

        # Simulate fzf selecting dim, then profile
        mock_run_fzf.side_effect = [dim_path_str2, "k1"] # First call returns dim, second returns profile
        # Simulate get_profile_env for the chosen profile
        mock_dim2.get_profile_env.return_value = {"KUBE_VAR": "k1_val"}

        mocked_mux_instance.handle_switch(None, None) # No args

        # Check fzf calls
        expected_fzf_calls = [
            call(sorted([dim_path_str1, dim_path_str2]), "Select Dimension"),
            call(sorted(["k1", "k2"]), f"Select Profile for '{dim_path_str2}'")
        ]
        assert mock_run_fzf.call_args_list == expected_fzf_calls
        
        # Check get_profile_env called only for the selected dim/profile
        mock_dim1.get_profile_env.assert_not_called()
        mock_dim2.get_profile_env.assert_called_once_with("k1")
        
        # Check stdout
        output = mock_stdout.write.call_args[0][0]
        assert "export KUBE_VAR='k1_val';" in output
        assert f"export {ENV_VAR_PREFIX}_KUBE_NS='k1';" in output # Check MUX_ACTIVE var

    @patch('mux.core.run_fzf')
    @patch('sys.stdout', new_callable=MagicMock)
    def test_handle_switch_interactive_fzf_cancel_dim(self, mock_stdout, mock_run_fzf, mocked_mux_instance):
        # Test fzf cancellation during dimension selection
        mocked_mux_instance.all_dimensions = {"dim1": MagicMock()}
        mock_run_fzf.return_value = None # Simulate cancellation
        
        mocked_mux_instance.handle_switch(None, None)
        
        mock_run_fzf.assert_called_once_with(sorted(["dim1"]), "Select Dimension")
        mock_stdout.write.assert_called_once_with(":") # Should output no-op

    @patch('mux.core.run_fzf')
    @patch('sys.stdout', new_callable=MagicMock)
    def test_handle_switch_interactive_fzf_cancel_profile(self, mock_stdout, mock_run_fzf, mocked_mux_instance):
        # Test fzf cancellation during profile selection
        dim_path_str = "dim1"
        mock_dim = MagicMock(spec=Dimension)
        mock_dim.get_profiles.return_value = {"p1": {}}
        mocked_mux_instance.all_dimensions = {dim_path_str: mock_dim}

        mock_run_fzf.return_value = None # Simulate cancellation

        mocked_mux_instance.handle_switch(dim_path_str, None)

        mock_run_fzf.assert_called_once_with(sorted(["p1"]), f"Select Profile for '{dim_path_str}'")
        mock_stdout.write.assert_called_once_with(":") # Should output no-op

    @patch('mux.core.run_fzf', side_effect=FzfNotInstalledError())
    @patch('mux.ui.console_err.print') # Mock print_error in ui module
    def test_handle_switch_interactive_fzf_not_installed(self, mock_console_print, mock_run_fzf, mocked_mux_instance):
        # Test fzf not installed during dimension selection
        mocked_mux_instance.all_dimensions = {"dim1": MagicMock()}
        
        # We expect the function to re-raise FzfNotInstalledError after printing
        with pytest.raises(FzfNotInstalledError):
            # Patch the console print method used by print_error
            with patch('mux.ui.console_err.print') as mock_console_print:
                mocked_mux_instance.handle_switch(None, None)
        
        # Check that console print was called with the error message
        mock_console_print.assert_called_once()
        assert "fzf' command not found" in mock_console_print.call_args[0][0]

    def test_handle_default(self, mocked_mux_instance):
        # Test setting default profile
        mock_dim = MagicMock()
        mock_dim.get_profiles.return_value = {"dev": {}, "prod": {}}
        mocked_mux_instance.all_dimensions = {"test/dim": mock_dim}
        
        mocked_mux_instance.handle_default("test/dim", "dev")
        
        mock_dim.set_configured_default_profile.assert_called_once_with("dev")
    
    def test_handle_default_dimension_not_found(self, mocked_mux_instance):
        # Test setting default for non-existent dimension
        mocked_mux_instance.all_dimensions = {}
        
        with pytest.raises(DimensionNotFoundError, match="Dimension 'nonexistent' not found"):
            mocked_mux_instance.handle_default("nonexistent", "dev")
    
    def test_handle_default_profile_not_found(self, mocked_mux_instance):
        # Test setting non-existent profile as default
        mock_dim = MagicMock()
        mock_dim.get_profiles.return_value = {"dev": {}, "prod": {}}
        mocked_mux_instance.all_dimensions = {"test/dim": mock_dim}
        
        with pytest.raises(ProfileNotFoundError, match="Profile 'nonexistent' not found for dimension 'test/dim'"):
            mocked_mux_instance.handle_default("test/dim", "nonexistent")

    # --- Tests for handle_auto_activate ---
    @patch('sys.stdout', new_callable=MagicMock)
    @patch('mux.core.generate_shell_commands')
    @patch('mux.core.get_active_profile_from_env')
    def test_handle_auto_activate(self, mock_get_active, mock_generate_cmds, mock_stdout, mocked_mux_instance):
        """Test auto-activating default profiles for inactive dimensions."""
        # Setup mock dimensions
        dim1 = MagicMock(spec=Dimension)
        dim1.get_effective_default_profile.return_value = "default1"
        dim1.get_profiles.return_value = {"default1": {"VAR1": "val1"}}
        dim1.get_profile_env.return_value = {"VAR1": "val1"}

        dim2 = MagicMock(spec=Dimension)
        dim2.get_effective_default_profile.return_value = "default2"
        dim2.get_profiles.return_value = {"other": {}, "default2": {"VAR2": "val2"}}
        dim2.get_profile_env.return_value = {"VAR2": "val2"}

        dim3_active = MagicMock(spec=Dimension) # Already active
        
        dim4_no_default = MagicMock(spec=Dimension) # Inactive, no default
        dim4_no_default.get_effective_default_profile.return_value = None
        
        dim5_missing_default = MagicMock(spec=Dimension) # Default set but profile missing
        dim5_missing_default.get_effective_default_profile.return_value = "missing"
        dim5_missing_default.get_profiles.return_value = {"other": {}} # 'missing' not here

        mocked_mux_instance.all_dimensions = {
            "dim1": dim1, 
            "dim2": dim2, 
            "dim3": dim3_active, 
            "dim4": dim4_no_default,
            "dim5": dim5_missing_default
        }
        
        # Mock which dimensions are active
        mock_get_active.side_effect = lambda dim: "active_profile" if dim == dim3_active else None

        # Mock generated commands
        mock_generate_cmds.side_effect = lambda target_dim_path_str, **kwargs: f"export CMD_FOR_{target_dim_path_str.upper()}"

        # Call the method
        mocked_mux_instance.handle_auto_activate()

        # Assertions
        assert mock_get_active.call_count == 5 # Called for each dimension
        
        # Should try to get default for inactive dims (1, 2, 4, 5)
        assert dim1.get_effective_default_profile.call_count == 1
        assert dim2.get_effective_default_profile.call_count == 1
        assert dim4_no_default.get_effective_default_profile.call_count == 1
        assert dim5_missing_default.get_effective_default_profile.call_count == 1
        assert dim3_active.get_effective_default_profile.call_count == 0 # Not called if active

        # Should check if default profile exists for dims with a default (1, 2, 5)
        assert dim1.get_profiles.call_count == 1
        assert dim2.get_profiles.call_count == 1
        assert dim5_missing_default.get_profiles.call_count == 1
        assert dim3_active.get_profiles.call_count == 0
        assert dim4_no_default.get_profiles.call_count == 0 # No default to check

        # Should get env for valid, existing defaults (1, 2)
        assert dim1.get_profile_env.call_count == 1
        dim1.get_profile_env.assert_called_once_with("default1")
        assert dim2.get_profile_env.call_count == 1
        dim2.get_profile_env.assert_called_once_with("default2")
        assert dim3_active.get_profile_env.call_count == 0
        assert dim4_no_default.get_profile_env.call_count == 0
        assert dim5_missing_default.get_profile_env.call_count == 0 # Profile didn't exist

        # Should generate commands only for dims where default was found and valid (1, 2)
        assert mock_generate_cmds.call_count == 2
        mock_generate_cmds.assert_any_call(
            target_dim_path_str="dim1", old_env=None, new_env={"VAR1": "val1"}, new_profile_name="default1"
        )
        mock_generate_cmds.assert_any_call(
            target_dim_path_str="dim2", old_env=None, new_env={"VAR2": "val2"}, new_profile_name="default2"
        )
        
        # Check stdout output
        expected_output = "export CMD_FOR_DIM1\nexport CMD_FOR_DIM2\n"
        mock_stdout.write.assert_called_once_with(expected_output)

    @patch('sys.stdout', new_callable=MagicMock)
    @patch('mux.core.generate_shell_commands')
    @patch('mux.core.get_active_profile_from_env', return_value=None)
    @patch('mux.core.print_warning')
    def test_handle_auto_activate_profile_load_error(self, mock_warning, mock_get_active, mock_generate_cmds, mock_stdout, mocked_mux_instance):
        """Test that errors during profile loading are handled gracefully."""
        dim1 = MagicMock(spec=Dimension)
        dim1.get_effective_default_profile.return_value = "default1"
        dim1.get_profiles.return_value = {"default1": {}}
        # Simulate error when getting env
        dim1.get_profile_env.side_effect = Exception("Failed to load env") 

        mocked_mux_instance.all_dimensions = {"dim1": dim1}
        
        mocked_mux_instance.handle_auto_activate()

        assert mock_warning.call_count == 1 # Warning should be printed
        assert "Error auto-activating" in mock_warning.call_args[0][0]
        assert "dim1" in mock_warning.call_args[0][0]
        mock_generate_cmds.assert_not_called() # No commands generated
        mock_stdout.write.assert_not_called() # Nothing printed to stdout

    @patch('sys.stdout', new_callable=MagicMock)
    @patch('mux.core.generate_shell_commands')
    @patch('mux.core.get_active_profile_from_env', return_value=None)
    @patch('mux.core.print_warning')
    def test_handle_auto_activate_profile_not_found_in_get_profiles(self, mock_warning, mock_get_active, mock_generate_cmds, mock_stdout, mocked_mux_instance):
        """Test warning when default profile is not in get_profiles result."""
        dim1 = MagicMock(spec=Dimension)
        dim1.get_effective_default_profile.return_value = "default1"
        # Default profile "default1" is missing here
        dim1.get_profiles.return_value = {"other_profile": {}} 
        dim1.get_profile_env.side_effect = ProfileNotFoundError("default1", "dim1") # Should not be called

        mocked_mux_instance.all_dimensions = {"dim1": dim1}
        
        mocked_mux_instance.handle_auto_activate()

        assert mock_warning.call_count == 1 # Warning should be printed
        assert "Default profile 'default1' for dimension 'dim1' not found." in mock_warning.call_args[0][0]
        dim1.get_profile_env.assert_not_called() # Should not try to load env
        mock_generate_cmds.assert_not_called() # No commands generated
        mock_stdout.write.assert_not_called() # Nothing printed to stdout