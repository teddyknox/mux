import pytest
import yaml
import json
import os
from pathlib import Path
from mux.dimension import Dimension

# --- Fixtures ---

@pytest.fixture
def mock_mux_dir(tmp_path):
    """Creates a temporary base mux directory."""
    mux_dir = tmp_path / ".mux"
    mux_dir.mkdir()
    return mux_dir

@pytest.fixture
def setup_manual_dimension(mock_mux_dir):
    """Sets up a dimension with manual profiles."""
    dim_path = mock_mux_dir / "kube"
    dim_path.mkdir()
    profiles_dir = dim_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "dev.env").write_text("KUBECONFIG=/path/to/dev\nNAMESPACE=dev-ns")
    (profiles_dir / "prod.env").write_text("KUBECONFIG=/path/to/prod\nNAMESPACE=prod-ns")
    (dim_path / "default.txt").write_text("dev")
    return dim_path

@pytest.fixture
def setup_yaml_dimension(mock_mux_dir):
    """Sets up a dimension with profiles.yaml."""
    dim_path = mock_mux_dir / "aws"
    dim_path.mkdir()
    yaml_content = {
        "personal": {"AWS_PROFILE": "pers", "AWS_REGION": "us-east-1"},
        "work": {"AWS_PROFILE": "work", "AWS_REGION": "us-west-2"},
    }
    (dim_path / "profiles.yaml").write_text(yaml.dump(yaml_content))
    (dim_path / "default.txt").write_text("personal")
    return dim_path

@pytest.fixture
def setup_dynamic_dimension(mock_mux_dir):
    """Sets up a dimension with profiles.py."""
    dim_path = mock_mux_dir / "gcp"
    dim_path.mkdir()
    script_content = """#!/usr/bin/env python3
import json
import sys

# parent_profile = sys.argv[1] if len(sys.argv) > 1 else ""
# print(f"Parent profile received: {parent_profile}", file=sys.stderr) # For debugging

profiles = {
    "proj-a": {"GCP_PROJECT": "project-a", "GCP_ZONE": "us-central1-a"},
    "proj-b": {"GCP_PROJECT": "project-b", "GCP_ZONE": "europe-west1-b"},
}
print(json.dumps(profiles))
"""
    script_path = dim_path / "profiles.py"
    script_path.write_text(script_content)
    os.chmod(script_path, 0o755) # Make executable
    (dim_path / "default.txt").write_text("proj-a")
    return dim_path

@pytest.fixture
def setup_precedence_dimension(mock_mux_dir):
    """Sets up a dimension with manual, yaml, and dynamic profiles to test precedence."""
    dim_path = mock_mux_dir / "precedence"
    dim_path.mkdir()

    # Manual
    profiles_dir = dim_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "manual_prof.env").write_text("SOURCE=manual") # Use .env extension

    # Yaml
    yaml_content = {"yaml_prof": {"SOURCE": "yaml"}, "manual_prof": {"SOURCE": "yaml_override"}}
    (dim_path / "profiles.yaml").write_text(yaml.dump(yaml_content))

    # Dynamic
    script_content = """#!/usr/bin/env python3
import json
profiles = {
    "dynamic_prof": {"SOURCE": "dynamic"},
    "yaml_prof": {"SOURCE": "dynamic_override"},
    "manual_prof": {"SOURCE": "dynamic_override_all"}
}
print(json.dumps(profiles))
"""
    script_path = dim_path / "profiles.py"
    script_path.write_text(script_content)
    os.chmod(script_path, 0o755) # Make executable
    (dim_path / "default.txt").write_text("dynamic_prof") # Default from dynamic
    return dim_path


# --- Test Cases ---

def test_load_manual_profiles(setup_manual_dimension):
    """Verify loading profiles from individual files."""
    dim = Dimension("kube", setup_manual_dimension)
    profiles = dim.get_profiles()
    assert "dev" in profiles
    assert "prod" in profiles
    assert profiles["dev"] == {"KUBECONFIG": "/path/to/dev", "NAMESPACE": "dev-ns"}
    assert profiles["prod"] == {"KUBECONFIG": "/path/to/prod", "NAMESPACE": "prod-ns"}
    assert dim.get_default_profile_name() == "dev"

def test_load_yaml_profiles(setup_yaml_dimension):
    """Verify loading profiles from profiles.yaml."""
    dim = Dimension("aws", setup_yaml_dimension)
    profiles = dim.get_profiles()
    assert "personal" in profiles
    assert "work" in profiles
    assert profiles["personal"] == {"AWS_PROFILE": "pers", "AWS_REGION": "us-east-1"}
    assert profiles["work"] == {"AWS_PROFILE": "work", "AWS_REGION": "us-west-2"}
    assert dim.get_default_profile_name() == "personal"

def test_load_dynamic_profiles(setup_dynamic_dimension, monkeypatch):
    """Verify loading profiles from profiles.py."""
    dim = Dimension("gcp", setup_dynamic_dimension)
    profiles = dim.get_profiles()
    assert "proj-a" in profiles
    assert "proj-b" in profiles
    assert profiles["proj-a"] == {"GCP_PROJECT": "project-a", "GCP_ZONE": "us-central1-a"}
    assert profiles["proj-b"] == {"GCP_PROJECT": "project-b", "GCP_ZONE": "europe-west1-b"}
    assert dim.get_default_profile_name() == "proj-a"

def test_profile_loading_precedence(setup_precedence_dimension, monkeypatch):
    """Verify that dynamic > yaml > manual precedence is followed."""
    dim = Dimension("precedence", setup_precedence_dimension)
    profiles = dim.get_profiles()

    # Should only contain profiles from the highest precedence source (dynamic)
    assert "dynamic_prof" in profiles
    assert "yaml_prof" in profiles
    assert "manual_prof" in profiles
    assert len(profiles) == 3 # Ensure no extras leaked from lower precedence

    # Check that the values are from the dynamic script
    assert profiles["dynamic_prof"]["SOURCE"] == "dynamic"
    assert profiles["yaml_prof"]["SOURCE"] == "dynamic_override"
    assert profiles["manual_prof"]["SOURCE"] == "dynamic_override_all"
    assert dim.get_default_profile_name() == "dynamic_prof"


def test_invalid_default_profile(mock_mux_dir, capsys):
    """Test behavior when default.txt points to a non-existent profile."""
    dim_path = mock_mux_dir / "invalid_default"
    dim_path.mkdir()
    profiles_dir = dim_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "real_prof.env").write_text("VAR=value") # Use .env extension
    (dim_path / "default.txt").write_text("fake_prof") # Non-existent default

    dim = Dimension("invalid_default", dim_path)
    # Initial default loading doesn't validate, we need to access effective_default
    effective = dim.get_effective_default_profile()
    captured = capsys.readouterr()

    assert dim.get_default_profile_name() is None # Default should be reset when found invalid
    assert effective is None
    warning_text = captured.err
    assert "Default profile 'fake_prof'" in warning_text
    assert "not found in loaded" in warning_text
    assert "real_prof" in dim.get_profiles() # The valid profile should still load


def test_invalid_yaml_format(mock_mux_dir, capsys):
    """Test behavior with incorrectly formatted profiles.yaml."""
    dim_path = mock_mux_dir / "invalid_yaml"
    dim_path.mkdir()
    # List instead of dict
    (dim_path / "profiles.yaml").write_text("- profile1: {VAR: val}")

    dim = Dimension("invalid_yaml", dim_path)
    # Force profile loading with non-silent mode to generate warnings
    dim._load_profiles(silent=False)
    captured = capsys.readouterr()

    assert not dim.get_profiles() # No profiles should be loaded
    # Check stderr for the warning
    assert "Error loading profiles from YAML" in captured.err
    assert "YAML root must" in captured.err # Match partial text
    assert "dictionary" in captured.err # Match partial text


def test_invalid_yaml_profile_entry(mock_mux_dir, capsys):
    """Test behavior with invalid entry within profiles.yaml."""
    dim_path = mock_mux_dir / "invalid_yaml_entry"
    dim_path.mkdir()
    yaml_content = {
        "good_prof": {"VAR1": "val1"},
        "bad_prof": "just a string" # Invalid value for a profile
    }
    (dim_path / "profiles.yaml").write_text(yaml.dump(yaml_content))

    dim = Dimension("invalid_yaml_entry", dim_path)
    # Force profile loading with non-silent mode to generate warnings
    dim._load_profiles(silent=False)
    captured = capsys.readouterr()

    profiles = dim.get_profiles()
    assert not profiles # Parsing likely stops, expect empty
    assert "bad_prof" not in profiles # Bad one should be skipped
    # Check stderr for the warning
    assert "Value for profile 'bad_prof' must be a dictionary" in captured.err # Check specific error part


def test_dynamic_script_error(mock_mux_dir, capsys, monkeypatch):
    """Test behavior when profiles.py fails to execute."""
    dim_path = mock_mux_dir / "script_error"
    dim_path.mkdir()
    script_content = """#!/usr/bin/env python3
import sys
print("Something went wrong", file=sys.stderr)
sys.exit(1)
"""
    script_path = dim_path / "profiles.py"
    script_path.write_text(script_content)
    os.chmod(script_path, 0o755) # Make executable

    dim = Dimension("script_error", dim_path)
    # Force profile loading with non-silent mode to generate warnings
    dim._load_profiles(silent=False)
    captured = capsys.readouterr()

    assert not dim.get_profiles()
    # assert "Warning: Error running profile script" in captured.err # Corrected warning start
    assert "Profile script" in captured.err and "failed (exit code" in captured.err # Check actual warning
    assert "Stderr:" in captured.err
    assert "Something went wrong" in captured.err


def test_dynamic_script_invalid_json(mock_mux_dir, capsys, monkeypatch):
    """Test behavior when profiles.py outputs invalid JSON."""
    dim_path = mock_mux_dir / "invalid_json"
    dim_path.mkdir()
    script_content = """#!/usr/bin/env python3
print("this is not json")
"""
    script_path = dim_path / "profiles.py"
    script_path.write_text(script_content)
    os.chmod(script_path, 0o755) # Make executable

    dim = Dimension("invalid_json", dim_path)
    # Force profile loading with non-silent mode to generate warnings
    dim._load_profiles(silent=False)
    captured = capsys.readouterr()

    assert not dim.get_profiles()
    # assert "Warning: Error running profile script" in captured.err # Check generic script error first
    assert "Configuration error in profile script" in captured.err # Check actual warning
    assert "Error \ndecoding JSON from script" in captured.err # Check specific error part
    # assert "Could not parse JSON output" in captured.err # Then specific JSON error
    assert "Output:" in captured.err
    assert "this is not json" in captured.err

def test_dynamic_script_wrong_json_structure(mock_mux_dir, capsys, monkeypatch):
    """Test behavior when profiles.py outputs JSON but not the expected dict structure."""
    dim_path = mock_mux_dir / "wrong_json"
    dim_path.mkdir()
    script_content = """#!/usr/bin/env python3
import json
print(json.dumps(["list", "not", "dict"]))
"""
    script_path = dim_path / "profiles.py"
    script_path.write_text(script_content)
    os.chmod(script_path, 0o755) # Make executable

    dim = Dimension("wrong_json", dim_path)
    # Force profile loading with non-silent mode to generate warnings
    dim._load_profiles(silent=False)
    captured = capsys.readouterr()

    assert not dim.get_profiles()
    # assert "Warning: Error running profile script" in captured.err # Check generic script error first
    assert "Configuration error in profile script" in captured.err # Check actual warning
    # assert "Invalid JSON structure" in captured.err # Then specific structure error
    assert "Script output\nmust be a JSON dictionary" in captured.err # Check specific error part
    # assert "Expected a dictionary at the top level" in captured.err # Check specific error


def test_set_default_profile(setup_manual_dimension):
    """Test setting the default profile."""
    dim = Dimension("kube", setup_manual_dimension)
    assert dim.get_default_profile_name() == "dev"

    success = dim.set_default_profile("prod")
    assert success
    assert dim.get_default_profile_name() == "prod"

    # Verify file content
    default_file = setup_manual_dimension / "default.txt"
    assert default_file.read_text() == "prod"

    # Reload dimension to check persistence
    dim_reloaded = Dimension("kube", setup_manual_dimension)
    assert dim_reloaded.get_default_profile_name() == "prod"


def test_set_nonexistent_default_profile(setup_manual_dimension, capsys):
    """Test setting a non-existent profile as default."""
    dim = Dimension("kube", setup_manual_dimension)
    original_default = dim.get_default_profile_name()

    success = dim.set_default_profile("nonexistent")
    captured = capsys.readouterr()

    assert not success
    assert dim.get_default_profile_name() == original_default # Should not change
    # Check that the warning message is printed
    # The warning message includes ANSI color codes, so we just check for the core text
    assert "Profile 'nonexistent' does not exist for dimension 'kube'" in captured.err
    assert "Available profiles" in captured.err 