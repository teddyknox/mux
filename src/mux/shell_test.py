import pytest
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

from mux.shell import get_active_profile_from_env, run_fzf
from mux.config import ENV_VAR_PREFIX
from mux.exceptions import FzfNotInstalledError
# Assume Dimension class has get_dim_path_str() for testing purposes
from mux.core import Dimension

# --- Tests for get_active_profile_from_env ---

@patch.dict(os.environ, {}, clear=True) # Start with clean environment
def test_get_active_profile_from_env_set():
    dim_path = Path("/fake/path/to/dim") # Path doesn't need to exist
    mock_dim = MagicMock(spec=Dimension)
    mock_dim.get_dim_path_str.return_value = "path/to/dim"
    mock_dim.name = "dim" # Add the name attribute
    
    # Construct env var name based on dim name (uppercase, replace slashes)
    env_var_name = f"{ENV_VAR_PREFIX}_DIM"
    os.environ[env_var_name] = "active_prof"
    
    assert get_active_profile_from_env(mock_dim) == "active_prof"
    # get_dim_path_str is no longer used by get_active_profile_from_env
    # mock_dim.get_dim_path_str.assert_called_once()

@patch.dict(os.environ, {}, clear=True)
def test_get_active_profile_from_env_not_set():
    dim_path = Path("/fake/path/to/dim")
    mock_dim = MagicMock(spec=Dimension)
    mock_dim.get_dim_path_str.return_value = "path/to/dim" # Keep for spec consistency if needed elsewhere
    mock_dim.name = "dim" # Add the name attribute
    
    # Ensure the relevant env var is NOT set
    env_var_name = f"{ENV_VAR_PREFIX}_DIM"
    if env_var_name in os.environ:
        del os.environ[env_var_name]
        
    assert get_active_profile_from_env(mock_dim) is None
    # get_dim_path_str is no longer used by get_active_profile_from_env
    # mock_dim.get_dim_path_str.assert_called_once()

def test_get_active_profile_from_env_no_method():
    # Test case where Dimension object might be missing the method
    mock_dim = MagicMock() # No spec, no get_dim_path_str
    assert get_active_profile_from_env(mock_dim) is None
    
# --- Tests for run_fzf ---

@patch('subprocess.run')
def test_run_fzf_success(mock_run):
    items = ["item1", "item2", "item3"]
    prompt = "Choose"
    mock_run.return_value = MagicMock(stdout="item2\n", stderr="", returncode=0)
    
    result = run_fzf(items, prompt)
    
    assert result == "item2"
    mock_run.assert_called_once()
    call_args, _ = mock_run.call_args
    command_list = call_args[0]
    assert command_list[0] == "fzf" # Check command
    assert "--prompt" in command_list
    assert f"{prompt}> " in command_list
    # Check options individually
    assert "--height" in command_list
    assert "6" in command_list
    assert "--border" in command_list
    assert "--layout=reverse" in command_list 
    assert mock_run.call_args.kwargs['input'] == "item1\nitem2\nitem3"

@patch('subprocess.run')
def test_run_fzf_no_prompt(mock_run):
    items = ["a", "b"]
    mock_run.return_value = MagicMock(stdout="b\n", stderr="", returncode=0)
    
    result = run_fzf(items)
    assert result == "b"
    mock_run.assert_called_once()
    call_args, _ = mock_run.call_args
    assert "--prompt" not in call_args[0]

@patch('subprocess.run')
def test_run_fzf_cancel(mock_run):
    items = ["a", "b"]
    mock_run.return_value = MagicMock(stdout="", stderr="", returncode=130) # Simulate Ctrl+C
    assert run_fzf(items, "Prompt") is None

@patch('subprocess.run')
def test_run_fzf_no_match(mock_run):
    items = ["a", "b"]
    mock_run.return_value = MagicMock(stdout="", stderr="", returncode=1) # Simulate no match
    assert run_fzf(items, "Prompt") is None

@patch('subprocess.run')
def test_run_fzf_other_error(mock_run):
    items = ["a", "b"]
    mock_run.return_value = MagicMock(stdout="", stderr="Some fzf error", returncode=2)
    assert run_fzf(items, "Prompt") is None # Should treat as cancellation for now

def test_run_fzf_not_installed():
    with patch('subprocess.run', side_effect=FileNotFoundError("[Errno 2] No such file or directory: 'fzf'")):
        with pytest.raises(FzfNotInstalledError):
            run_fzf(["a"], "Prompt")

def test_run_fzf_empty_list():
    assert run_fzf([]) is None