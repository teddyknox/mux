import pytest
import yaml
import json
import sys
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

from mux.profiles import (
    parse_env_file,
    load_profiles_from_files,
    load_profiles_from_yaml,
    load_profiles_from_script,
    load_profiles_for_dimension
)
from mux.exceptions import InvalidConfigError
from mux.config import PROFILE_ENV_FILE_SUFFIX

# --- Tests for parse_env_file ---

def test_parse_env_file_success(tmp_path):
    env_file = tmp_path / "test.env"
    env_file.write_text("VAR1=value1\n# Comment\nVAR2 = value 2 \n\nEMPTY=\n")
    expected = {"VAR1": "value1", "VAR2": "value 2", "EMPTY": ""}
    assert parse_env_file(env_file) == expected

def test_parse_env_file_no_equals(tmp_path):
    env_file = tmp_path / "test.env"
    env_file.write_text("VAR1=value1\nINVALID_LINE\nVAR2=value2")
    expected = {"VAR1": "value1", "VAR2": "value2"}
    assert parse_env_file(env_file) == expected

def test_parse_env_file_not_found(tmp_path):
    env_file = tmp_path / "nonexistent.env"
    with pytest.raises(InvalidConfigError, match="Error reading env file"): # Check for specific error pattern
        parse_env_file(env_file)

# --- Tests for load_profiles_from_files ---

def test_load_profiles_from_files_success(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / f"dev{PROFILE_ENV_FILE_SUFFIX}").write_text("API_KEY=dev_key\nENDPOINT=dev_endpoint")
    (profiles_dir / f"prod{PROFILE_ENV_FILE_SUFFIX}").write_text("API_KEY=prod_key\nENDPOINT=prod_endpoint")
    (profiles_dir / "ignore_this.txt").touch() # Non-env file
    (profiles_dir / f"{PROFILE_ENV_FILE_SUFFIX}").touch() # Env file with empty name
    
    expected = {
        "dev": {"API_KEY": "dev_key", "ENDPOINT": "dev_endpoint"},
        "prod": {"API_KEY": "prod_key", "ENDPOINT": "prod_endpoint"}
    }
    assert load_profiles_from_files(profiles_dir) == expected

def test_load_profiles_from_files_dir_not_exist(tmp_path):
    profiles_dir = tmp_path / "nonexistent_profiles"
    assert load_profiles_from_files(profiles_dir) == {}

@patch('mux.profiles.print_warning')
def test_load_profiles_from_files_parse_error(mock_print_warning, tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / f"good{PROFILE_ENV_FILE_SUFFIX}").write_text("VAR=good_val")
    # Create a file that will cause parse_env_file to raise an error
    # Mocking the error isn't easy, so let's make it unreadable
    bad_file = profiles_dir / f"bad{PROFILE_ENV_FILE_SUFFIX}"
    bad_file.touch()
    os.chmod(bad_file, 0o000) # Make unreadable

    expected = {"good": {"VAR": "good_val"}}
    result = load_profiles_from_files(profiles_dir)
    assert result == expected
    mock_print_warning.assert_called_once()
    assert "Skipping profile 'bad'" in mock_print_warning.call_args[0][0]

    # Clean up permissions for tmp_path removal
    os.chmod(bad_file, 0o644)

# --- Tests for load_profiles_from_yaml ---

def test_load_profiles_from_yaml_success(tmp_path):
    yaml_file = tmp_path / "profiles.yaml"
    yaml_content = {
        "dev": {"VAR1": "yaml_dev1", "VAR2": 123}, # Test int conversion
        "prod": {"VAR1": "yaml_prod1", "VAR2": True} # Test bool conversion
    }
    yaml_file.write_text(yaml.dump(yaml_content))
    expected = {
        "dev": {"VAR1": "yaml_dev1", "VAR2": "123"},
        "prod": {"VAR1": "yaml_prod1", "VAR2": "True"}
    }
    assert load_profiles_from_yaml(yaml_file) == expected

def test_load_profiles_from_yaml_file_not_exist(tmp_path):
    yaml_file = tmp_path / "nonexistent.yaml"
    assert load_profiles_from_yaml(yaml_file) == {}

def test_load_profiles_from_yaml_empty_file(tmp_path):
    yaml_file = tmp_path / "empty.yaml"
    yaml_file.touch()
    assert load_profiles_from_yaml(yaml_file) == {}

def test_load_profiles_from_yaml_invalid_structure(tmp_path):
    yaml_file = tmp_path / "invalid.yaml"
    # YAML representing a list, not a dictionary
    yaml_file.write_text(""" 
- profile1: value1
- profile2: value2
""")
    with pytest.raises(InvalidConfigError, match="YAML root must be a dictionary"):
        load_profiles_from_yaml(yaml_file)

def test_load_profiles_from_yaml_profile_not_dict(tmp_path):
    yaml_file = tmp_path / "invalid_profile.yaml"
    yaml_content = {"dev": "not_a_dict"}
    yaml_file.write_text(yaml.dump(yaml_content))
    with pytest.raises(InvalidConfigError, match="Value for profile 'dev' must be a dictionary"):
        load_profiles_from_yaml(yaml_file)

def test_load_profiles_from_yaml_parse_error(tmp_path):
    yaml_file = tmp_path / "parse_error.yaml"
    yaml_file.write_text("dev: { key: 'value\n': invalid_yaml }")
    with pytest.raises(InvalidConfigError, match="Error parsing YAML"):
        load_profiles_from_yaml(yaml_file)

# --- Tests for load_profiles_from_script ---

@patch('subprocess.run')
def test_load_profiles_from_script_success(mock_run, tmp_path):
    script_file = tmp_path / "profiles.py"
    script_file.touch()
    os.chmod(script_file, 0o755) # Make executable

    script_output = {
        "script_dev": {"SCRIPT_VAR": "dev_val", "NUM": 456},
        "script_prod": {"SCRIPT_VAR": "prod_val", "BOOL": False}
    }
    mock_run.return_value = MagicMock(
        stdout=json.dumps(script_output), stderr="", returncode=0
    )

    expected = {
        "script_dev": {"SCRIPT_VAR": "dev_val", "NUM": "456"},
        "script_prod": {"SCRIPT_VAR": "prod_val", "BOOL": "False"}
    }
    result = load_profiles_from_script(script_file)
    assert result == expected
    mock_run.assert_called_once_with(
        [str(script_file)], capture_output=True, text=True, check=True, timeout=5
    )

@patch('subprocess.run')
def test_load_profiles_from_script_with_parent(mock_run, tmp_path):
    script_file = tmp_path / "profiles.py"
    script_file.touch()
    os.chmod(script_file, 0o755)
    mock_run.return_value = MagicMock(stdout="{}", stderr="", returncode=0)

    load_profiles_from_script(script_file, "parent_profile_name")
    mock_run.assert_called_once_with(
        [str(script_file), "parent_profile_name"], # Check parent arg passed
        capture_output=True, text=True, check=True, timeout=5
    )

def test_load_profiles_from_script_not_exist(tmp_path):
    script_file = tmp_path / "nonexistent.py"
    assert load_profiles_from_script(script_file) == {}

@patch('mux.profiles.print_warning')
def test_load_profiles_from_script_not_executable(mock_print_warning, tmp_path):
    script_file = tmp_path / "not_exec.py"
    script_file.touch() # Not executable
    assert load_profiles_from_script(script_file) == {}
    mock_print_warning.assert_called_once()
    # Check the content of the first argument passed to the mock
    assert "not executable" in mock_print_warning.call_args[0][0]

@patch('subprocess.run')
@patch('mux.profiles.print_warning')
def test_load_profiles_from_script_error_exit(mock_print_warning, mock_run, tmp_path):
    script_file = tmp_path / "error.py"
    script_file.touch()
    os.chmod(script_file, 0o755)
    mock_run.side_effect = subprocess.CalledProcessError(1, [str(script_file)], stderr="Script failed badly")

    assert load_profiles_from_script(script_file) == {}
    mock_print_warning.assert_called_once()
    assert "failed (exit code 1)" in mock_print_warning.call_args[0][0]
    assert "Script failed badly" in mock_print_warning.call_args[0][0]

@patch('subprocess.run')
def test_load_profiles_from_script_invalid_json(mock_run, tmp_path):
    script_file = tmp_path / "invalid_json.py"
    script_file.touch()
    os.chmod(script_file, 0o755)
    mock_run.return_value = MagicMock(stdout="not valid json", stderr="", returncode=0)

    with pytest.raises(InvalidConfigError, match="Error decoding JSON from script"):
        load_profiles_from_script(script_file)

@patch('subprocess.run')
def test_load_profiles_from_script_json_not_dict(mock_run, tmp_path):
    script_file = tmp_path / "json_list.py"
    script_file.touch()
    os.chmod(script_file, 0o755)
    mock_run.return_value = MagicMock(stdout="[1, 2, 3]", stderr="", returncode=0)

    with pytest.raises(InvalidConfigError, match="Script output must be a JSON dictionary"):
        load_profiles_from_script(script_file)

@patch('subprocess.run')
def test_load_profiles_from_script_profile_value_not_dict(mock_run, tmp_path):
    script_file = tmp_path / "profile_list.py"
    script_file.touch()
    os.chmod(script_file, 0o755)
    script_output = {"dev": ["invalid"]}
    mock_run.return_value = MagicMock(stdout=json.dumps(script_output), stderr="", returncode=0)

    with pytest.raises(InvalidConfigError, match="Value for profile 'dev' in script output must be a dictionary"):
        load_profiles_from_script(script_file)

@patch('subprocess.run')
@patch('mux.profiles.print_warning')
def test_load_profiles_from_script_timeout(mock_print_warning, mock_run, tmp_path):
    script_file = tmp_path / "timeout.py"
    script_file.touch()
    os.chmod(script_file, 0o755)
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=[str(script_file)], timeout=5)

    assert load_profiles_from_script(script_file) == {}
    mock_print_warning.assert_called_once()
    # Check the content of the first argument passed to the mock
    assert "timed out after 5 seconds" in mock_print_warning.call_args[0][0]

# --- Tests for load_profiles_for_dimension (precedence) ---

@patch('mux.profiles.load_profiles_from_files')
@patch('mux.profiles.load_profiles_from_yaml')
@patch('mux.profiles.load_profiles_from_script')
def test_load_profiles_for_dimension_precedence_files(
    mock_load_script, mock_load_yaml, mock_load_files, tmp_path
):
    dim_path = tmp_path / "dim"
    dim_path.mkdir()
    (dim_path / "profiles").mkdir() # Presence triggers files check
    (dim_path / "profiles.yaml").touch()
    (dim_path / "profiles.py").touch()

    mock_load_files.return_value = {"file_prof": {"VAR": "file"}}
    mock_load_yaml.return_value = {"yaml_prof": {"VAR": "yaml"}}
    mock_load_script.return_value = {"script_prof": {"VAR": "script"}}

    result = load_profiles_for_dimension(dim_path)
    assert result == {"file_prof": {"VAR": "file"}}
    mock_load_files.assert_called_once()
    mock_load_yaml.assert_not_called()
    mock_load_script.assert_not_called()

@patch('mux.profiles.load_profiles_from_files')
@patch('mux.profiles.load_profiles_from_yaml')
@patch('mux.profiles.load_profiles_from_script')
def test_load_profiles_for_dimension_precedence_yaml(
    mock_load_script, mock_load_yaml, mock_load_files, tmp_path
):
    dim_path = tmp_path / "dim"
    dim_path.mkdir()
    # No profiles dir
    (dim_path / "profiles.yaml").touch() # Presence triggers yaml check
    (dim_path / "profiles.py").touch()

    mock_load_files.return_value = {}
    mock_load_yaml.return_value = {"yaml_prof": {"VAR": "yaml"}}
    mock_load_script.return_value = {"script_prof": {"VAR": "script"}}

    result = load_profiles_for_dimension(dim_path)
    assert result == {"yaml_prof": {"VAR": "yaml"}}
    mock_load_files.assert_called_once() # Still checks dir first
    mock_load_yaml.assert_called_once()
    mock_load_script.assert_not_called()

@patch('mux.profiles.load_profiles_from_files')
@patch('mux.profiles.load_profiles_from_yaml')
@patch('mux.profiles.load_profiles_from_script')
def test_load_profiles_for_dimension_precedence_script(
    mock_load_script, mock_load_yaml, mock_load_files, tmp_path
):
    dim_path = tmp_path / "dim"
    dim_path.mkdir()
    # No profiles dir, no yaml file
    (dim_path / "profiles.py").touch() # Presence triggers script check
    os.chmod(dim_path / "profiles.py", 0o755)

    mock_load_files.return_value = {}
    mock_load_yaml.return_value = {}
    mock_load_script.return_value = {"script_prof": {"VAR": "script"}}

    result = load_profiles_for_dimension(dim_path)
    assert result == {"script_prof": {"VAR": "script"}}
    mock_load_files.assert_called_once() # Checks dir
    mock_load_yaml.assert_called_once() # Checks yaml
    mock_load_script.assert_called_once()

@patch('mux.profiles.load_profiles_from_files')
@patch('mux.profiles.load_profiles_from_yaml')
@patch('mux.profiles.load_profiles_from_script')
def test_load_profiles_for_dimension_none_found(
    mock_load_script, mock_load_yaml, mock_load_files, tmp_path
):
    dim_path = tmp_path / "dim"
    dim_path.mkdir()
    # No profile sources exist

    mock_load_files.return_value = {}
    mock_load_yaml.return_value = {}
    mock_load_script.return_value = {}

    result = load_profiles_for_dimension(dim_path)
    assert result == {}
    mock_load_files.assert_called_once()
    mock_load_yaml.assert_called_once()
    mock_load_script.assert_called_once()

@patch('mux.profiles.print_warning')
@patch('mux.profiles.load_profiles_from_files', side_effect=InvalidConfigError("Bad files"))
@patch('mux.profiles.load_profiles_from_yaml')
@patch('mux.profiles.load_profiles_from_script')
def test_load_profiles_for_dimension_error_fallback_files(
    mock_load_script, mock_load_yaml, mock_load_files, mock_print_warning, tmp_path
):
    dim_path = tmp_path / "dim"
    dim_path.mkdir()
    (dim_path / "profiles").mkdir() # Trigger files check
    (dim_path / "profiles.yaml").touch()

    mock_load_yaml.return_value = {"yaml_prof": {"VAR": "yaml"}}

    result = load_profiles_for_dimension(dim_path)

    assert result == {"yaml_prof": {"VAR": "yaml"}} # Falls back to YAML
    mock_print_warning.assert_called_once()
    assert "Error loading profiles from directory" in mock_print_warning.call_args[0][0]
    mock_load_files.assert_called_once()
    mock_load_yaml.assert_called_once()
    mock_load_script.assert_not_called() 