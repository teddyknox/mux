import pytest
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

from mux.shell import get_active_profile_from_env, generate_shell_commands, run_fzf
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
    
    env_var_name = f"{ENV_VAR_PREFIX}_PATH_TO_DIM"
    os.environ[env_var_name] = "active_prof"
    
    assert get_active_profile_from_env(mock_dim) == "active_prof"
    mock_dim.get_dim_path_str.assert_called_once()

@patch.dict(os.environ, {}, clear=True)
def test_get_active_profile_from_env_not_set():
    dim_path = Path("/fake/path/to/dim")
    mock_dim = MagicMock(spec=Dimension)
    mock_dim.get_dim_path_str.return_value = "path/to/dim"
    
    # Ensure the relevant env var is NOT set
    env_var_name = f"{ENV_VAR_PREFIX}_PATH_TO_DIM"
    if env_var_name in os.environ:
        del os.environ[env_var_name]
        
    assert get_active_profile_from_env(mock_dim) is None
    mock_dim.get_dim_path_str.assert_called_once()

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
    assert "40%" in command_list
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

# --- Tests for generate_shell_commands ---

# Helper to parse the generated command string for easier assertion
def parse_commands(command_str: str) -> dict:
    exports = {}
    unsets = set()
    commands = command_str.strip().split(';')
    for cmd in commands:
        cmd = cmd.strip()
        if not cmd: continue
        if cmd.startswith('export '):
            part = cmd[len('export '):]
            key, value = part.split('=', 1)
            # Crudely unescape single quotes for comparison
            value = value.strip("'").replace("'\\''", "'")
            exports[key] = value
        elif cmd.startswith('unset '):
            unsets.add(cmd[len('unset '):])
    return {'export': exports, 'unset': unsets}

def test_generate_shell_commands_simple_switch():
    old_env = {"VAR1": "old_val1", "COMMON": "same", "OLD_MUX": "old_prof"}
    new_env = {"VAR2": "new_val2", "COMMON": "same", "NEW_MUX": "new_prof"}
    target_dim = "target/dim"
    new_profile = "new_profile_name"
    mux_active_var = f"{ENV_VAR_PREFIX}_TARGET_DIM"
    
    expected_exports = {
        "VAR2": "new_val2", 
        "COMMON": "same",
        "NEW_MUX": "new_prof", 
        mux_active_var: new_profile
    }
    expected_unsets = {"VAR1", "OLD_MUX", mux_active_var}
    
    result_str = generate_shell_commands(target_dim, old_env, new_env, new_profile)
    result_parsed = parse_commands(result_str)
    
    assert result_parsed['export'] == expected_exports
    assert result_parsed['unset'] == expected_unsets
    # Check order: unsets before exports
    assert result_str.find('unset VAR1') < result_str.find('export VAR2')
    assert result_str.find('unset OLD_MUX') < result_str.find('export NEW_MUX')

def test_generate_shell_commands_switch_to_same_value():
    # Switching where a var exists in both, but value changes
    old_env = {"VAR1": "old_val1", "COMMON": "val_old"}
    new_env = {"VAR1": "new_val1", "COMMON": "val_new"}
    target_dim = "target"
    new_profile = "prof2"
    mux_active_var = f"{ENV_VAR_PREFIX}_TARGET"
    
    expected_exports = {"VAR1": "new_val1", "COMMON": "val_new", mux_active_var: "prof2"}
    expected_unsets = {mux_active_var} # Correctly expect MUX_ACTIVE to be unset
    
    result_str = generate_shell_commands(target_dim, old_env, new_env, new_profile)
    result_parsed = parse_commands(result_str)

    assert result_parsed['export'] == expected_exports
    assert result_parsed['unset'] == expected_unsets

def test_generate_shell_commands_activate_from_none():
    old_env = None
    new_env = {"VAR1": "val1"}
    target_dim = "target"
    new_profile = "prof1"
    mux_active_var = f"{ENV_VAR_PREFIX}_TARGET"
    
    expected_exports = {"VAR1": "val1", mux_active_var: "prof1"}
    expected_unsets = set() # Nothing to unset from old_env
    
    result_str = generate_shell_commands(target_dim, old_env, new_env, new_profile)
    result_parsed = parse_commands(result_str)
    
    assert result_parsed['export'] == expected_exports
    assert result_parsed['unset'] == expected_unsets

@patch.dict(os.environ, {"MUX_ACTIVE_TARGET": "manual"}, clear=True)
def test_generate_shell_commands_activate_from_none_mux_var_exists():
    # Test activating when MUX_ACTIVE was already set (e.g., manually)
    old_env = None 
    new_env = {"VAR1": "val1"}
    target_dim = "target"
    new_profile = "prof1"
    mux_active_var = f"{ENV_VAR_PREFIX}_TARGET"
    
    expected_exports = {"VAR1": "val1", mux_active_var: "prof1"}
    # Should unset the manually set MUX_ACTIVE var before exporting new one
    expected_unsets = {mux_active_var} 
    
    result_str = generate_shell_commands(target_dim, old_env, new_env, new_profile)
    result_parsed = parse_commands(result_str)
    
    assert result_parsed['export'] == expected_exports
    assert result_parsed['unset'] == expected_unsets
    assert result_str.find(f'unset {mux_active_var}') < result_str.find(f'export {mux_active_var}')

def test_generate_shell_commands_deactivate_to_none():
    # Simulating deactivation (although switch command doesn't do this directly)
    old_env = {"VAR1": "val1", "MUX_ACTIVE_TARGET": "prof1"}
    new_env = {} # Empty new env
    target_dim = "target"
    new_profile = "" # Simulate setting MUX_ACTIVE to empty? Or should it unset?
                     # Let's assume the caller handles deactivation logic.
                     # This test checks unsetting based on old_env.
    mux_active_var = f"{ENV_VAR_PREFIX}_TARGET"

    expected_exports = {mux_active_var: ""} # Set MUX_ACTIVE to empty?
    expected_unsets = {"VAR1", mux_active_var}
    
    result_str = generate_shell_commands(target_dim, old_env, new_env, new_profile)
    result_parsed = parse_commands(result_str)
    
    assert result_parsed['export'] == expected_exports
    assert result_parsed['unset'] == expected_unsets

def test_generate_shell_commands_value_with_quotes():
    old_env = None
    new_env = {"KEY": "value with 'single' quotes"}
    target_dim = "target"
    new_profile = "prof_quotes"
    mux_active_var = f"{ENV_VAR_PREFIX}_TARGET"

    expected_exports = { "KEY": "value with 'single' quotes", mux_active_var: "prof_quotes"}
    expected_unsets = set()
    
    result_str = generate_shell_commands(target_dim, old_env, new_env, new_profile)
    result_parsed = parse_commands(result_str)

    assert result_parsed['export'] == expected_exports
    assert result_parsed['unset'] == expected_unsets
    # Check the actual command string for correct quoting
    # Need to match the '\\'' escape sequence generated
    assert "export KEY='value with '\\''single'\\'' quotes';" in result_str