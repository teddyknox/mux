import pytest
import yaml
import json
import sys
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
from typing import Dict

from mux.profiles import (
    parse_env_file,
    load_profiles_from_files,
    load_profiles_from_yaml,
    load_profiles_from_script,
    load_profiles_for_dimension
)
from mux.exceptions import InvalidConfigError
from mux.config import PROFILE_ENV_FILE_SUFFIX

# Helper function to create dummy profile files/dirs for testing
def setup_test_dimension(tmp_path: Path, config: Dict):
    """Sets up a dimension directory structure in tmp_path based on config."""
    dim_name = config.get("dim_name", "test_dim")
    # The tmp_path passed might be like tmp_path / "subdir"
    # Ensure the parent of the dimension path exists first
    dim_parent_path = tmp_path
    dim_parent_path.mkdir(parents=True, exist_ok=True)
    
    dim_path = dim_parent_path / dim_name
    dim_path.mkdir() # Now create the actual dimension directory

    if "profiles_dir" in config:
        profiles_path = dim_path / "profiles"
        profiles_path.mkdir()
        for name, content in config["profiles_dir"].items():
            # Assume .env suffix if not provided, based on other tests
            suffix = ".env" if not name.endswith(".env") else ""
            p_file = profiles_path / f"{name}{suffix}"
            p_file.write_text(content)

    if "profiles_yaml" in config:
        yaml_path = dim_path / "profiles.yaml"
        yaml_path.write_text(config["profiles_yaml"])

    if "profiles_py" in config:
        py_path = dim_path / "profiles.py"
        py_path.write_text(config["profiles_py"])
        # Make executable
        # Use try-except for potential permission errors in restricted envs
        try:
            os.chmod(py_path, py_path.stat().st_mode | 0o111) # Add execute permissions
        except OSError as e:
            print(f"Warning: Could not make {py_path} executable: {e}")

    if "default" in config:
        default_file = dim_path / "default.txt"
        default_file.write_text(config["default"])

    return dim_path

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

def test_load_yaml_success(tmp_path):
    yaml_content = """
    profileA:
        VAR1: valueA1
        VAR2: valueA2
    profileB:
        VAR1: valueB1
    """
    dim_path = setup_test_dimension(tmp_path, {"profiles_yaml": yaml_content})
    yaml_file = dim_path / "profiles.yaml"
    
    expected = {
        "profileA": {"VAR1": "valueA1", "VAR2": "valueA2"},
        "profileB": {"VAR1": "valueB1"}
    }
    assert load_profiles_from_yaml(yaml_file) == expected

def test_load_yaml_non_existent(tmp_path):
    yaml_file = tmp_path / "non_existent" / "profiles.yaml"
    assert load_profiles_from_yaml(yaml_file) == {}

def test_load_yaml_empty_file(tmp_path):
    dim_path = setup_test_dimension(tmp_path, {"profiles_yaml": ""})
    yaml_file = dim_path / "profiles.yaml"
    assert load_profiles_from_yaml(yaml_file) == {}

def test_load_yaml_invalid_yaml(tmp_path):
    dim_path = setup_test_dimension(tmp_path, {"profiles_yaml": "profileA: VAR1: valueA1\n  VAR2"}) # Invalid indentation
    yaml_file = dim_path / "profiles.yaml"
    with pytest.raises(InvalidConfigError, match="Error parsing YAML"):
        load_profiles_from_yaml(yaml_file)

def test_load_yaml_not_a_dict(tmp_path):
    dim_path = setup_test_dimension(tmp_path, {"profiles_yaml": "- item1\n- item2"}) # List instead of dict
    yaml_file = dim_path / "profiles.yaml"
    with pytest.raises(InvalidConfigError, match="YAML root must be a dictionary"):
        load_profiles_from_yaml(yaml_file)

def test_load_yaml_profile_value_not_dict(tmp_path):
    yaml_content = """
    profileA: valueA # Should be a dict
    profileB:
        VAR1: valueB1
    """
    dim_path = setup_test_dimension(tmp_path, {"profiles_yaml": yaml_content})
    yaml_file = dim_path / "profiles.yaml"
    with pytest.raises(InvalidConfigError, match="Value for profile 'profileA' must be a dictionary"):
        load_profiles_from_yaml(yaml_file)

# --- Tests for load_profiles_from_script ---

def test_load_script_success(tmp_path):
    script_content = """#!/usr/bin/env python3
import json
print(json.dumps({
    'script_prof1': {'SCRIPT_VAR': 'val1', 'COMMON': 'script'},
    'script_prof2': {'SCRIPT_VAR': 'val2'}
}))
"""
    dim_path = setup_test_dimension(tmp_path, {"profiles_py": script_content})
    script_file = dim_path / "profiles.py"
    expected = {
        "script_prof1": {"SCRIPT_VAR": "val1", "COMMON": "script"},
        "script_prof2": {"SCRIPT_VAR": "val2"}
    }
    assert load_profiles_from_script(script_file) == expected

def test_load_script_with_parent_profile_arg(tmp_path):
    script_content = """#!/usr/bin/env python3
import json
import sys
parent = sys.argv[1] if len(sys.argv) > 1 else 'default_parent'
print(json.dumps({
    f'prof_{parent}': {'PARENT': parent}
}))
"""
    dim_path = setup_test_dimension(tmp_path, {"profiles_py": script_content})
    script_file = dim_path / "profiles.py"
    parent_name = "specific_parent"
    expected = {
        f"prof_{parent_name}": {"PARENT": parent_name}
    }
    assert load_profiles_from_script(script_file, parent_profile=parent_name) == expected

def test_load_script_non_existent(tmp_path):
    script_file = tmp_path / "non_existent" / "profiles.py"
    assert load_profiles_from_script(script_file) == {}

def test_load_script_not_executable(tmp_path, capsys):
    script_content = "#!/usr/bin/env python3\nprint('{}')"
    dim_path = setup_test_dimension(tmp_path, {"profiles_py": script_content})
    script_file = dim_path / "profiles.py"
    os.chmod(script_file, 0o644) # Ensure NOT executable
    assert load_profiles_from_script(script_file) == {}
    captured = capsys.readouterr()
    assert "not executable" in captured.err # Check warning

def test_load_script_execution_error(tmp_path, capsys):
    script_content = "#!/usr/bin/env python3\nimport sys\nsys.exit(1)"
    dim_path = setup_test_dimension(tmp_path, {"profiles_py": script_content})
    script_file = dim_path / "profiles.py"
    assert load_profiles_from_script(script_file) == {}
    captured = capsys.readouterr()
    assert "failed (exit code 1)" in captured.err

def test_load_script_timeout(tmp_path, capsys, monkeypatch):
    # Mock subprocess.run to simulate timeout
    def mock_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=kwargs.get('cmd', args[0]), timeout=0.1)
    monkeypatch.setattr(subprocess, "run", mock_run)

    script_content = "#!/usr/bin/env python3\nimport time\ntime.sleep(1)\nprint('{}')"
    dim_path = setup_test_dimension(tmp_path, {"profiles_py": script_content})
    script_file = dim_path / "profiles.py"
    
    assert load_profiles_from_script(script_file) == {}
    captured = capsys.readouterr()
    assert "timed out" in captured.err

def test_load_script_invalid_json_output(tmp_path):
    script_content = "#!/usr/bin/env python3\nprint('this is not json')"
    dim_path = setup_test_dimension(tmp_path, {"profiles_py": script_content})
    script_file = dim_path / "profiles.py"
    with pytest.raises(InvalidConfigError, match="Error decoding JSON"):
        load_profiles_from_script(script_file)

def test_load_script_json_not_dict(tmp_path):
    script_content = "#!/usr/bin/env python3\nimport json\nprint(json.dumps(['list', 'not', 'dict']))"
    dim_path = setup_test_dimension(tmp_path, {"profiles_py": script_content})
    script_file = dim_path / "profiles.py"
    with pytest.raises(InvalidConfigError, match="Script output must be a JSON dictionary"):
        load_profiles_from_script(script_file)

def test_load_script_profile_value_not_dict(tmp_path):
    script_content = """#!/usr/bin/env python3
import json
print(json.dumps({
    'profA': 'not a dict',
    'profB': {'VAR': 'value'}
}))
"""
    dim_path = setup_test_dimension(tmp_path, {"profiles_py": script_content})
    script_file = dim_path / "profiles.py"
    with pytest.raises(InvalidConfigError, match="Value for profile 'profA' in script output must be a dictionary"):
        load_profiles_from_script(script_file)

# --- Tests for load_profiles_for_dimension (Priority & Fallback) ---

def test_load_dimension_priority_files_over_yaml_over_script(tmp_path):
    """Test that profiles/ takes precedence over yaml, which takes precedence over script."""
    files_config = {"file_prof": "FILE_VAR=file_val"}
    yaml_content = "yaml_prof:\n  YAML_VAR: yaml_val"
    script_content = "#!/usr/bin/env python3\nimport json\nprint(json.dumps({'script_prof': {'SCRIPT_VAR': 'script_val'}}))"
    
    # Case 1: All exist, files should win
    dim_path_all = setup_test_dimension(tmp_path / "all", {
        "dim_name": "dim_all",
        "profiles_dir": files_config,
        "profiles_yaml": yaml_content,
        "profiles_py": script_content
    })
    expected_files = {"file_prof": {"FILE_VAR": "file_val"}}
    assert load_profiles_for_dimension(dim_path_all) == expected_files

    # Case 2: Yaml and Script exist, Yaml should win
    dim_path_yaml_script = setup_test_dimension(tmp_path / "yaml_script", {
        "dim_name": "dim_yaml_script",
        # No profiles_dir
        "profiles_yaml": yaml_content,
        "profiles_py": script_content
    })
    expected_yaml = {"yaml_prof": {"YAML_VAR": "yaml_val"}}
    assert load_profiles_for_dimension(dim_path_yaml_script) == expected_yaml
    
    # Case 3: Only Script exists, Script should win
    dim_path_script = setup_test_dimension(tmp_path / "script", {
        "dim_name": "dim_script",
        # No profiles_dir or profiles_yaml
        "profiles_py": script_content
    })
    expected_script = {"script_prof": {"SCRIPT_VAR": "script_val"}}
    assert load_profiles_for_dimension(dim_path_script) == expected_script

def test_load_dimension_no_sources(tmp_path):
    """Test behavior when no profile sources are found."""
    dim_path = tmp_path / "empty_dim"
    dim_path.mkdir()
    assert load_profiles_for_dimension(dim_path) == {}

def test_load_dimension_error_fallback(tmp_path, capsys):
    """Test fallback when a higher priority source exists but has errors."""
    # Files dir exists but contains bad file, should fall back to yaml
    files_config_bad = {"bad_prof": "INVALID_CONTENT"} # Assume parse_env_file handles this gracefully or raises InvalidConfigError
    yaml_content = "yaml_prof:\n  YAML_VAR: yaml_val"
    
    # Mock parse_env_file to raise error for this test
    original_parse = parse_env_file
    def mock_parse_env_file(file_path: Path):
        if "bad_prof" in file_path.name:
             raise InvalidConfigError("bad parse", str(file_path))
        return original_parse(file_path) # call original for other cases if any

    dim_path_file_error = setup_test_dimension(tmp_path / "file_err", {
        "dim_name": "dim_file_err",
        "profiles_dir": files_config_bad,
        "profiles_yaml": yaml_content
    })
    
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("mux.profiles.parse_env_file", mock_parse_env_file)
        # It seems load_profiles_from_files catches the error and returns {}, 
        # so load_profiles_for_dimension proceeds to yaml. Let's adapt the test.
        # The warning comes from load_profiles_from_files directly.
        # assert load_profiles_for_dimension(dim_path_file_error) == {"yaml_prof": {"YAML_VAR": "yaml_val"}}

        # Rework: load_profiles_from_files itself handles the error and prints a warning.
        # We need to test that load_profiles_for_dimension correctly receives the empty dict
        # from the failed file load and proceeds to load from YAML.
        
        # Step 1: Test load_profiles_from_files with error
        profiles_dir = dim_path_file_error / "profiles"
        assert load_profiles_from_files(profiles_dir) == {}
        captured = capsys.readouterr()
        assert "Skipping profile 'bad_prof'" in captured.err

        # Step 2: Test load_profiles_for_dimension picks up YAML after files fail
        assert load_profiles_for_dimension(dim_path_file_error) == {"yaml_prof": {"YAML_VAR": "yaml_val"}}


    # Yaml file exists but is invalid, should fall back to script
    yaml_content_invalid = "key: val:\n nested"
    script_content = "#!/usr/bin/env python3\nimport json\nprint(json.dumps({'script_prof': {'SCRIPT_VAR': 'script_val'}}))"
    
    dim_path_yaml_error = setup_test_dimension(tmp_path / "yaml_err", {
        "dim_name": "dim_yaml_err",
        "profiles_yaml": yaml_content_invalid,
        "profiles_py": script_content
    })
    
    expected_script = {"script_prof": {"SCRIPT_VAR": "script_val"}}
    assert load_profiles_for_dimension(dim_path_yaml_error) == expected_script
    captured = capsys.readouterr() # Check warning for yaml error
    assert "Error loading profiles from YAML" in captured.err


# TODO: Add tests for parent_dim interaction once its structure is clearer
# For now, load_profiles_from_script tests passing the name. 