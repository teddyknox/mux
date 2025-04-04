# tests/test_core.py
import pytest
import sys
import os
from unittest.mock import patch, MagicMock, call
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

    def test_get_user_default_profile_success(self, dimension_with_path, monkeypatch, tmp_path):
        # Mock DEFAULTS_DIR to use tmp_path
        mock_defaults_dir = tmp_path / "defaults"
        mock_defaults_dir.mkdir()
        monkeypatch.setattr('mux.core.DEFAULTS_DIR', mock_defaults_dir)
        
        user_default_file = mock_defaults_dir / "test_dim" # Based on _get_user_default_file_path
        user_default_file.write_text("  dev  ")
        assert dimension_with_path.get_user_default_profile() == "dev"

    def test_get_user_default_profile_not_found(self, dimension_with_path, monkeypatch, tmp_path):
        mock_defaults_dir = tmp_path / "defaults"
        mock_defaults_dir.mkdir()
        monkeypatch.setattr('mux.core.DEFAULTS_DIR', mock_defaults_dir)
        assert dimension_with_path.get_user_default_profile() is None
        
    def test_get_user_default_profile_complex_path(self, tmp_path, monkeypatch):
        # Test _get_user_default_file_path conversion
        root_path = tmp_path / "root"
        root_path.mkdir()
        child_path = root_path / "child.dim"
        child_path.mkdir()
        root = Dimension("root", root_path)
        child = Dimension("child.dim", child_path, root)
        
        mock_defaults_dir = tmp_path / "defaults"
        mock_defaults_dir.mkdir()
        monkeypatch.setattr('mux.core.DEFAULTS_DIR', mock_defaults_dir)
        
        expected_default_filename = "root_child.dim" # From _get_user_default_file_path
        user_default_file = mock_defaults_dir / expected_default_filename
        user_default_file.write_text("complex_prof")
        
        assert child.get_user_default_profile() == "complex_prof"

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

    @patch('mux.core.print_success')
    def test_set_user_default_profile_success(self, mock_print_success, dimension_with_path, monkeypatch, tmp_path, mock_profiles):
        # Mock get_profiles to allow setting 'dev'
        dimension_with_path.get_profiles = MagicMock(return_value=mock_profiles)
        
        mock_defaults_dir = tmp_path / "defaults"
        # Don't mkdir here, let the method do it
        monkeypatch.setattr('mux.core.DEFAULTS_DIR', mock_defaults_dir)

        dimension_with_path.set_user_default_profile("dev")

        expected_file = mock_defaults_dir / "test_dim"
        assert mock_defaults_dir.is_dir()
        assert expected_file.is_file()
        assert expected_file.read_text() == "dev\n"
        mock_print_success.assert_called_once()
        assert "Set default profile" in mock_print_success.call_args[0][0]
        assert "to 'dev'" in mock_print_success.call_args[0][0]
        dimension_with_path.get_profiles.assert_called_once() # Verify profile check

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


class TestMux:
    @pytest.fixture
    def mock_dims_dir(self, monkeypatch, tmp_path):
        dims_dir = tmp_path / "dims"
        dims_dir.mkdir()
        monkeypatch.setattr('mux.core.DIMS_DIR', dims_dir)
        return dims_dir
    
    @pytest.fixture
    def mux_instance(self):
        # Patch discovery during fixture creation to avoid file system ops
        with patch('mux.core.Mux._discover_dimensions') as mock_discover:
            mux = Mux()
            # Ensure initialization attributes exist even with patched discovery
            if not hasattr(mux, 'root_dimensions'):
                mux.root_dimensions = []
            if not hasattr(mux, 'all_dimensions'):
                 mux.all_dimensions = {}
            return mux
    
    def test_init(self, mock_dims_dir):
        # Test Mux initialization - uses real discovery
        (mock_dims_dir / "dim1").mkdir()
        (mock_dims_dir / "dim2").mkdir()

        mux = Mux()
        assert hasattr(mux, 'root_dimensions')
        assert hasattr(mux, 'all_dimensions')
        assert len(mux.root_dimensions) == 2
        assert isinstance(mux.root_dimensions[0], Dimension)
        assert mux.root_dimensions[0].name == "dim1"
        assert mux.root_dimensions[1].name == "dim2"
        assert "dim1" in mux.all_dimensions
        assert "dim2" in mux.all_dimensions

    def test_discover_dimensions_empty(self, mock_dims_dir):
        # Test discovery when DIMS_DIR is empty
        mux = Mux()
        assert mux.root_dimensions == []
        assert mux.all_dimensions == {}

    def test_discover_dimensions_hierarchy(self, mock_dims_dir):
        # Create nested directory structure
        dim1_path = mock_dims_dir / "dim1"
        dim1_path.mkdir()
        dim2_path = mock_dims_dir / "dim2"
        dim2_path.mkdir()
        child_path = dim2_path / "child"
        child_path.mkdir()
        grandchild_path = child_path / "grandchild"
        grandchild_path.mkdir()
        # Add a file to ignore
        (dim1_path / "some_file.txt").touch()
        (child_path / "another_file").touch()

        # Initialize Mux to trigger discovery
        mux = Mux()

        # Assert root dimensions
        assert len(mux.root_dimensions) == 2
        root_names = sorted([d.name for d in mux.root_dimensions])
        assert root_names == ["dim1", "dim2"]

        # Find specific dimensions for easier assertions
        dim1 = next(d for d in mux.root_dimensions if d.name == "dim1")
        dim2 = next(d for d in mux.root_dimensions if d.name == "dim2")

        # Assert dim1 hierarchy (no children)
        assert dim1.parent is None
        assert dim1.children == []

        # Assert dim2 hierarchy
        assert dim2.parent is None
        assert len(dim2.children) == 1
        child = dim2.children[0]
        assert isinstance(child, Dimension)
        assert child.name == "child"
        assert child.path == child_path
        assert child.parent == dim2

        # Assert child hierarchy
        assert len(child.children) == 1
        grandchild = child.children[0]
        assert isinstance(grandchild, Dimension)
        assert grandchild.name == "grandchild"
        assert grandchild.path == grandchild_path
        assert grandchild.parent == child
        assert grandchild.children == []

        # Assert flat dimension dictionary created by __init__ after discovery
        assert "dim1" in mux.all_dimensions
        assert mux.all_dimensions["dim1"] == dim1
        assert "dim2" in mux.all_dimensions
        assert mux.all_dimensions["dim2"] == dim2
        assert "dim2/child" in mux.all_dimensions
        assert mux.all_dimensions["dim2/child"] == child
        assert "dim2/child/grandchild" in mux.all_dimensions
        assert mux.all_dimensions["dim2/child/grandchild"] == grandchild
        assert len(mux.all_dimensions) == 4 # Ensure no extra entries

    def test_get_all_dimensions_flat(self, mock_dims_dir):
        # Relies on real discovery via __init__
        (mock_dims_dir / "dim1").mkdir()
        dim2_path = mock_dims_dir / "dim2"
        dim2_path.mkdir()
        (dim2_path / "child").mkdir()
        
        mux = Mux()
        
        expected_keys = ["dim1", "dim2", "dim2/child"]
        # Order might vary, check presence and values
        assert sorted(mux.all_dimensions.keys()) == sorted(expected_keys)
        assert isinstance(mux.all_dimensions["dim1"], Dimension)
        assert isinstance(mux.all_dimensions["dim2"], Dimension)
        assert isinstance(mux.all_dimensions["dim2/child"], Dimension)
        assert mux.all_dimensions["dim2/child"].parent.name == "dim2"
        
    def test_get_all_dimensions_flat_nested(self, mock_dims_dir):
        # Relies on real discovery via __init__
        root_path = mock_dims_dir / "root"
        root_path.mkdir()
        child_path = root_path / "child"
        child_path.mkdir()
        grandchild_path = child_path / "grandchild"
        grandchild_path.mkdir()
        
        mux = Mux()
        
        expected_keys = ["root", "root/child", "root/child/grandchild"]
        assert sorted(mux.all_dimensions.keys()) == sorted(expected_keys)
        assert isinstance(mux.all_dimensions["root"], Dimension)
        assert isinstance(mux.all_dimensions["root/child"], Dimension)
        assert isinstance(mux.all_dimensions["root/child/grandchild"], Dimension)
        assert mux.all_dimensions["root/child"].parent.name == "root"
        assert mux.all_dimensions["root/child/grandchild"].parent.name == "child"

    def test_get_dimension(self, mux_instance):
        # Test dimension lookup
        mock_dim = MagicMock()
        mux_instance.all_dimensions = {"test/path": mock_dim}
        
        result = mux_instance.get_dimension("test/path")
        assert result == mock_dim
        
        # Test non-existent dimension
        assert mux_instance.get_dimension("nonexistent") is None
    
    @patch('mux.core.print_warning')
    @patch('mux.core.display_status_tree')
    def test_handle_status_empty(self, mock_display, mock_warning, mux_instance):
        # Test handling status when no dimensions exist
        mux_instance.root_dimensions = []
        
        mux_instance.handle_status()
        
        mock_warning.assert_called_once()
        mock_display.assert_not_called()
    
    @patch('mux.core.print_warning')
    @patch('mux.core.display_status_tree')
    def test_handle_status(self, mock_display, mock_warning, mux_instance):
        # Test handling status with dimensions
        mock_dims = [MagicMock(), MagicMock()]
        mux_instance.root_dimensions = mock_dims
        
        mux_instance.handle_status()
        
        mock_warning.assert_not_called()
        mock_display.assert_called_once_with(mock_dims)
    
    @patch('mux.core.display_show_table')
    @patch.dict(os.environ, {}, clear=True)
    def test_handle_show(self, mock_display, mux_instance):
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
        mux_instance.all_dimensions = {dim_path_str: mock_dim}

        mux_instance.handle_show(dim_path_str)

        # Verify get_profile_env was called with the active profile name from env
        mock_dim.get_profile_env.assert_called_once_with(profile_name)
        # Verify display is called with the correct args
        mock_display.assert_called_once_with(dim_path_str, profile_name, env_vars)

    @patch('mux.core.display_show_table')
    @patch.dict(os.environ, {}, clear=True)
    def test_handle_show_inactive(self, mock_display, mux_instance):
        # Test handling show for an *inactive* dimension
        dim_path_str = "test/dim"
        mux_active_var = f"{ENV_VAR_PREFIX}_TEST_DIM"
        if mux_active_var in os.environ:
            del os.environ[mux_active_var]

        mock_dim = MagicMock(spec=Dimension)
        mock_dim.get_dim_path_str.return_value = dim_path_str
        mux_instance.all_dimensions = {dim_path_str: mock_dim}

        mux_instance.handle_show(dim_path_str)

        # Verify get_profile_env was NOT called
        mock_dim.get_profile_env.assert_not_called()
        # Verify display is called indicating inactive
        mock_display.assert_called_once_with(dim_path_str, None, None)

    @patch('mux.core.display_show_table')
    def test_handle_show_dimension_not_found(self, mock_display, mux_instance):
        # Test handling show for non-existent dimension (no change needed here)
        mux_instance.all_dimensions = {}
        with pytest.raises(DimensionNotFoundError, match="Dimension 'nonexistent' not found"):
            mux_instance.handle_show("nonexistent")
        mock_display.assert_not_called()
    
    @patch('sys.stdout', new_callable=MagicMock)
    @patch.dict(os.environ, {}, clear=True)
    def test_handle_switch(self, mock_stdout, mux_instance):
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
        mux_instance.all_dimensions = {dim_path_str: mock_dim}
        
        mux_instance.handle_switch(dim_path_str, new_profile_name)

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
    def test_handle_switch_change_profile(self, mock_stdout, mux_instance):
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
        mux_instance.all_dimensions = {dim_path_str: mock_dim}
        
        mux_instance.handle_switch(dim_path_str, new_profile_name)
        
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
    def test_handle_switch_to_already_active(self, mock_stdout, mux_instance):
        # Test switching to the profile that is already active
        dim_path_str = "test/dim"
        profile_name = "dev"
        mux_active_var = f"{ENV_VAR_PREFIX}_TEST_DIM"
        os.environ[mux_active_var] = profile_name
        
        mock_dim = MagicMock(spec=Dimension)
        mock_dim.get_dim_path_str.return_value = dim_path_str
        mock_dim.get_profiles.return_value = {"dev": {}, "prod": {}} 
        mux_instance.all_dimensions = {dim_path_str: mock_dim}

        # Patch the print method of the console_err object in the ui module
        with patch('mux.ui.console_err.print') as mock_console_print:
            mux_instance.handle_switch(dim_path_str, profile_name)
            
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
    def test_handle_switch_profile_not_found(self, mux_instance): # Removed mock_generate
        # Test switching to non-existent profile (no change needed here)
        dim_path_str = "test/dim"
        mock_dim = MagicMock(spec=Dimension)
        mock_dim.get_dim_path_str.return_value = dim_path_str
        mock_dim.get_profiles.return_value = {"dev": {}, "prod": {}}
        mux_instance.all_dimensions = {dim_path_str: mock_dim}
        
        with pytest.raises(ProfileNotFoundError, match="Profile 'nonexistent' not found for dimension 'test/dim'"):
            mux_instance.handle_switch(dim_path_str, "nonexistent")
        
        mock_dim.get_profiles.assert_called_once()
        mock_dim.get_profile_env.assert_not_called()

    @patch('mux.core.run_fzf')
    @patch('sys.stdout', new_callable=MagicMock)
    def test_handle_switch_interactive_dim_only(self, mock_stdout, mock_run_fzf, mux_instance):
        # Test interactive mode (dimension only specified)
        dim_path_str = "test/dim"
        mock_dim = MagicMock(spec=Dimension)
        mock_dim.get_profiles.return_value = {"prof1": {}, "prof2": {}}
        mux_instance.all_dimensions = {dim_path_str: mock_dim}
        
        # Simulate fzf selecting "prof2"
        mock_run_fzf.return_value = "prof2"
        # Simulate get_profile_env returning something for the chosen profile
        mock_dim.get_profile_env.return_value = {"SELECTED": "prof2_val"}
        
        mux_instance.handle_switch(dim_path_str, None) # Profile is None
        
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
    def test_handle_switch_interactive_no_args(self, mock_stdout, mock_run_fzf, mux_instance):
        # Test interactive mode (no arguments specified)
        dim_path_str1 = "dim1"
        dim_path_str2 = "kube/ns"
        mock_dim1 = MagicMock(spec=Dimension)
        mock_dim1.get_profiles.return_value = {"d1p1": {}}
        mock_dim2 = MagicMock(spec=Dimension)
        mock_dim2.get_profiles.return_value = {"k1": {}, "k2": {}}
        mux_instance.all_dimensions = {dim_path_str1: mock_dim1, dim_path_str2: mock_dim2}

        # Simulate fzf selecting dim, then profile
        mock_run_fzf.side_effect = [dim_path_str2, "k1"] # First call returns dim, second returns profile
        # Simulate get_profile_env for the chosen profile
        mock_dim2.get_profile_env.return_value = {"KUBE_VAR": "k1_val"}

        mux_instance.handle_switch(None, None) # No args

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
    def test_handle_switch_interactive_fzf_cancel_dim(self, mock_stdout, mock_run_fzf, mux_instance):
        # Test fzf cancellation during dimension selection
        mux_instance.all_dimensions = {"dim1": MagicMock()}
        mock_run_fzf.return_value = None # Simulate cancellation
        
        mux_instance.handle_switch(None, None)
        
        mock_run_fzf.assert_called_once_with(sorted(["dim1"]), "Select Dimension")
        mock_stdout.write.assert_called_once_with(":") # Should output no-op

    @patch('mux.core.run_fzf')
    @patch('sys.stdout', new_callable=MagicMock)
    def test_handle_switch_interactive_fzf_cancel_profile(self, mock_stdout, mock_run_fzf, mux_instance):
        # Test fzf cancellation during profile selection
        dim_path_str = "dim1"
        mock_dim = MagicMock(spec=Dimension)
        mock_dim.get_profiles.return_value = {"p1": {}}
        mux_instance.all_dimensions = {dim_path_str: mock_dim}

        mock_run_fzf.return_value = None # Simulate cancellation

        mux_instance.handle_switch(dim_path_str, None)

        mock_run_fzf.assert_called_once_with(sorted(["p1"]), f"Select Profile for '{dim_path_str}'")
        mock_stdout.write.assert_called_once_with(":") # Should output no-op

    @patch('mux.core.run_fzf', side_effect=FzfNotInstalledError())
    @patch('mux.ui.console_err.print') # Mock print_error in ui module
    def test_handle_switch_interactive_fzf_not_installed(self, mock_console_print, mock_run_fzf, mux_instance):
        # Test fzf not installed during dimension selection
        mux_instance.all_dimensions = {"dim1": MagicMock()}
        
        # We expect the function to re-raise FzfNotInstalledError after printing
        with pytest.raises(FzfNotInstalledError):
            # Patch the console print method used by print_error
            with patch('mux.ui.console_err.print') as mock_console_print:
                mux_instance.handle_switch(None, None)
        
        # Check that console print was called with the error message
        mock_console_print.assert_called_once()
        assert "fzf' command not found" in mock_console_print.call_args[0][0]

    def test_handle_default(self, mux_instance):
        # Test setting default profile
        mock_dim = MagicMock()
        mock_dim.get_profiles.return_value = {"dev": {}, "prod": {}}
        mux_instance.all_dimensions = {"test/dim": mock_dim}
        
        mux_instance.handle_default("test/dim", "dev")
        
        mock_dim.set_configured_default_profile.assert_called_once_with("dev")
    
    def test_handle_default_dimension_not_found(self, mux_instance):
        # Test setting default for non-existent dimension
        mux_instance.all_dimensions = {}
        
        with pytest.raises(DimensionNotFoundError, match="Dimension 'nonexistent' not found"):
            mux_instance.handle_default("nonexistent", "dev")
    
    def test_handle_default_profile_not_found(self, mux_instance):
        # Test setting non-existent profile as default
        mock_dim = MagicMock()
        mock_dim.get_profiles.return_value = {"dev": {}, "prod": {}}
        mux_instance.all_dimensions = {"test/dim": mock_dim}
        
        with pytest.raises(ProfileNotFoundError, match="Profile 'nonexistent' not found for dimension 'test/dim'"):
            mux_instance.handle_default("test/dim", "nonexistent")