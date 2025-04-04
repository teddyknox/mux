import pytest
from unittest.mock import patch, MagicMock, call
import argparse
import sys
import os
from pathlib import Path
import subprocess
import contextlib

# Module to test
from mux import cli
from mux.config import DIMS_DIR, DEFAULTS_DIR

# Import the CLI entrypoint and helpers
from mux.cli import main, find_dimension, print_shell_commands
from mux.dimension import Dimension
from mux.utils import MUX_DIR_PATH
from mux.state import get_active_profile_env_var, get_profile_var_env_name

# Use rich's test console for capturing output
from rich.console import Console

# Fixture to set up a mock dimension structure
@pytest.fixture
def mock_dims(tmp_path):
    mux_dir = tmp_path / ".mux"
    mux_dir.mkdir()
    # os.environ["MUX_DIR_PATH"] = str(mux_dir) # Override default for tests - Let's use patching instead
    # MUX_DIR_PATH.mkdir(exist_ok=True) # Ensure the default path used by modules exists too

    # Dimension 1: kube (manual profiles)
    kube_path = mux_dir / "kube"
    kube_path.mkdir()
    kube_profiles = kube_path / "profiles"
    kube_profiles.mkdir()
    (kube_profiles / "dev.env").write_text("KUBECONFIG=dev_conf\nNAMESPACE=dev_ns")
    (kube_profiles / "prod.env").write_text("KUBECONFIG=prod_conf\nNAMESPACE=prod_ns")
    (kube_path / "default.txt").write_text("dev")

    # Dimension 2: aws (yaml profiles)
    aws_path = mux_dir / "aws"
    aws_path.mkdir()
    (aws_path / "profiles.yaml").write_text("""
    personal:
        AWS_PROFILE: pers
        AWS_REGION: us-east-1
    work:
        AWS_PROFILE: work
        AWS_REGION: us-west-2
    """)
    (aws_path / "default.txt").write_text("personal")

    # Dimension 3: gcp (dynamic script)
    gcp_path = mux_dir / "gcp"
    gcp_path.mkdir()
    script_content = """
import json, sys
parent=sys.argv[1] if len(sys.argv) > 1 else ''
print(json.dumps({
    'proj-a': {'PROJECT': 'a', 'PARENT': parent},
    'proj-b': {'PROJECT': 'b', 'PARENT': parent}
}))
"""
    py_path = gcp_path / "profiles.py"
    py_path.write_text(script_content)
    os.chmod(py_path, 0o755) # Make executable
    (gcp_path / "default.txt").write_text("proj-a")

    # Dimension 4: Child dimension (under kube)
    ns_path = kube_path / "namespace" # Nested under kube
    ns_path.mkdir()
    (ns_path / "profiles.yaml").write_text("""
    frontend:
        SVC_NAME: fe
    backend:
        SVC_NAME: be
    """)
    # No default for child

    yield mux_dir # Provide the temp mux dir path to tests

    # Cleanup environment override - No longer needed
    # if "MUX_DIR_PATH" in os.environ:
    #     del os.environ["MUX_DIR_PATH"]

# Helper context manager for patching MUX_DIR_PATH consistently
@contextlib.contextmanager
def patch_mux_dir(path):
    with patch('mux.utils.MUX_DIR_PATH', path), \
         patch('mux.dimension.MUX_DIR_PATH', path), \
         patch('mux.cli.MUX_DIR_PATH', path):
        yield

# --- Test Status Command ---

# Use parametrize to test with and without active profiles set
@pytest.mark.parametrize("active_envs", [
    {},
    {"MUX_ACTIVE_KUBE": "prod", "MUX_VAR_KUBE_NAMESPACE": "prod-ns"},
    {"MUX_ACTIVE_KUBE": "dev", "MUX_ACTIVE_AWS": "work", "MUX_ACTIVE_GCP": "proj-b"}
])
def test_status_command(mock_dims, capsys, active_envs):
    # Use clear=True to ensure only these test env vars are set
    with patch.dict(os.environ, active_envs, clear=True):
        # Use the context manager to patch MUX_DIR_PATH in all relevant modules
        with patch_mux_dir(mock_dims):
            with patch('sys.argv', ['mux', 'status']):
                main() # Run the CLI main function

    captured = capsys.readouterr()
    output = captured.out # Contains both stdout and potentially stderr warnings
    
    # Basic checks for stdout content
    assert "Mux Status" in output
    assert "kube" in output
    assert "aws" in output
    assert "gcp" in output
    assert "namespace" in output # Check for child dim name
    # Check for the actual tree structure leading to the child
    assert "┗━━ kube" in output # Parent is last root
    assert "    ┗━━ namespace" in output # Child is nested under parent

    # Check active/default status based on parametrize
    if "MUX_ACTIVE_KUBE" in active_envs:
        assert f"kube -> {active_envs['MUX_ACTIVE_KUBE']}" in output
        if active_envs['MUX_ACTIVE_KUBE'] == 'dev':
             assert "(default)" in output.split('kube')[1].split('\n')[0]
    else:
        assert "kube ->" not in output # Check if not active
        assert "(default: dev)" in output # Should show default

    if "MUX_ACTIVE_AWS" in active_envs:
        assert f"aws -> {active_envs['MUX_ACTIVE_AWS']}" in output
    else:
         assert "(default: personal)" in output

    if "MUX_ACTIVE_GCP" in active_envs:
        assert f"gcp -> {active_envs['MUX_ACTIVE_GCP']}" in output
    else:
         assert "(default: proj-a)" in output

    # Child dim checks (never active in this test setup)
    assert "namespace ->" not in output
    assert "(no active/default)" in output.split('namespace')[1]

# --- Test Show Command ---

@patch.dict(os.environ, {
    "MUX_ACTIVE_KUBE": "dev",
    "MUX_VAR_KUBE_KUBECONFIG": "dev_conf",
    "MUX_VAR_KUBE_NAMESPACE": "dev_ns",
    "MUX_ACTIVE_AWS": "work", # Set this too for find_dimension
    "MUX_VAR_AWS_AWS_PROFILE": "work",
    "MUX_VAR_AWS_AWS_REGION": "us-west-2"
}, clear=True)
def test_show_command_active(mock_dims, capsys):
    with patch_mux_dir(mock_dims):
        with patch('sys.argv', ['mux', 'show', 'kube']):
            main()
    
    captured = capsys.readouterr()
    output = captured.out
    assert "Active Environment for 'kube' (dev)" in output
    assert "KUBECONFIG" in output
    assert "dev_conf" in output
    assert "NAMESPACE" in output
    assert "dev_ns" in output
    assert "AWS_PROFILE" not in output # Ensure other dim vars aren't shown

def test_show_command_inactive(mock_dims, capsys):
    with patch_mux_dir(mock_dims):
        with patch.dict(os.environ, {}, clear=True): # Ensure no active profile
            with patch('sys.argv', ['mux', 'show', 'kube']):
                main()
    captured = capsys.readouterr()
    assert "No active profile for dimension 'kube'" in captured.out

def test_show_command_nonexistent_dim(mock_dims, capsys):
    with patch_mux_dir(mock_dims):
        with patch('sys.argv', ['mux', 'show', 'nonexistent']):
            with pytest.raises(SystemExit): # Expect exit due to error
                main()
    captured = capsys.readouterr()
    assert "Error: Dimension 'nonexistent' not found" in captured.err

# --- Test Default Command ---

def test_default_command_success(mock_dims, capsys):
    kube_dim_path = mock_dims / "kube"
    default_file = kube_dim_path / "default.txt"
    assert default_file.read_text() == "dev" # Verify initial state

    with patch_mux_dir(mock_dims):
        with patch('sys.argv', ['mux', 'default', 'kube', 'prod']):
            main()
    
    captured = capsys.readouterr()
    assert "Success: Default profile for dimension 'kube' set to 'prod'" in captured.out
    assert default_file.read_text() == "prod" # Verify file updated

def test_default_command_nonexistent_dim(mock_dims, capsys):
    with patch_mux_dir(mock_dims):
        with patch('sys.argv', ['mux', 'default', 'fake', 'prof']):
             with pytest.raises(SystemExit):
                main()
    captured = capsys.readouterr()
    assert "Error: Dimension 'fake' not found" in captured.err

def test_default_command_nonexistent_profile(mock_dims, capsys):
    with patch_mux_dir(mock_dims):
        with patch('sys.argv', ['mux', 'default', 'kube', 'fake']):
             with pytest.raises(SystemExit):
                main()
    captured = capsys.readouterr()
    assert "Error: Profile 'fake' not found for dimension 'kube'" in captured.err
    # Check for presence of each profile individually, ignoring order
    assert "Available profiles:" in captured.err
    assert "dev" in captured.err
    assert "prod" in captured.err

# --- Test Switch Command (prints commands) ---

@patch('mux.cli.print_shell_commands') # Mock the helper that prints
@patch.dict(os.environ, {}, clear=True) # Start with clean env
def test_switch_command_success_no_previous(mock_print_cmds, mock_dims, capsys):
    with patch_mux_dir(mock_dims):
        with patch('sys.argv', ['mux', 'switch', 'kube', 'prod']):
            main()
            
    mock_print_cmds.assert_called_once()
    commands = mock_print_cmds.call_args[0][0]
    expected_commands = [
        # No unset commands as nothing was active for 'kube'
        "export MUX_VAR_KUBE_KUBECONFIG='prod_conf'",
        "export MUX_VAR_KUBE_NAMESPACE='prod_ns'",
        "export MUX_ACTIVE_KUBE='prod'"
    ]
    assert commands == expected_commands
    
    captured = capsys.readouterr()
    # Check success message printed to stderr
    assert "Switched dimension 'kube' to profile 'prod'" in captured.err 

@patch('mux.cli.print_shell_commands') # Mock the helper that prints
@patch.dict(os.environ, {"MUX_ACTIVE_KUBE": "dev", "MUX_VAR_KUBE_NAMESPACE": "dev_ns"}, clear=True)
def test_switch_command_success_with_previous(mock_print_cmds, mock_dims, capsys):
    with patch_mux_dir(mock_dims):
        with patch('sys.argv', ['mux', 'switch', 'kube', 'prod']):
            main()
            
    mock_print_cmds.assert_called_once()
    commands = mock_print_cmds.call_args[0][0]
    expected_commands = [
        "unset MUX_VAR_KUBE_NAMESPACE", # Unset previous var
        "export MUX_VAR_KUBE_KUBECONFIG='prod_conf'", # Set new vars
        "export MUX_VAR_KUBE_NAMESPACE='prod_ns'",
        "export MUX_ACTIVE_KUBE='prod'" # Set active profile
    ]
    assert set(commands) == set(expected_commands) # Order of unset/export might vary slightly
    assert len(commands) == len(expected_commands)
    assert commands[-1] == expected_commands[-1] # Active profile should be last export
    
    captured = capsys.readouterr()
    assert "Switched dimension 'kube' to profile 'prod'" in captured.err

@patch('mux.cli.print_shell_commands') # Mock the helper that prints
def test_switch_command_nonexistent_dim(mock_print_cmds, mock_dims, capsys):
    with patch_mux_dir(mock_dims):
        with patch('sys.argv', ['mux', 'switch', 'fake', 'prof']):
            with pytest.raises(SystemExit):
                main()
    captured = capsys.readouterr()
    assert "Error: Dimension 'fake' not found" in captured.err
    mock_print_cmds.assert_not_called()

@patch('mux.cli.print_shell_commands') # Mock the helper that prints
def test_switch_command_nonexistent_profile(mock_print_cmds, mock_dims, capsys):
    with patch_mux_dir(mock_dims):
        with patch('sys.argv', ['mux', 'switch', 'kube', 'fake']):
            with pytest.raises(SystemExit):
                main()
    captured = capsys.readouterr()
    assert "Error: Profile 'fake' not found for dimension 'kube'" in captured.err
    # Check for presence of each profile individually, ignoring order
    assert "Available profiles:" in captured.err
    assert "dev" in captured.err
    assert "prod" in captured.err
    mock_print_cmds.assert_not_called()

# TODO: Add tests for FZF integration once implemented

# ... existing tests ... 