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
    script_content = """
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
    (dim_path / "profiles.py").write_text(script_content)
    # Make executable if needed (though subprocess with 'python' might not require it)
    # os.chmod(dim_path / "profiles.py", 0o755)
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
    (profiles_dir / "manual_prof").write_text("SOURCE=manual")

    # Yaml
    yaml_content = {"yaml_prof": {"SOURCE": "yaml"}, "manual_prof": {"SOURCE": "yaml_override"}}
    (dim_path / "profiles.yaml").write_text(yaml.dump(yaml_content))

    # Dynamic
    script_content = """
import json
profiles = {
    "dynamic_prof": {"SOURCE": "dynamic"},
    "yaml_prof": {"SOURCE": "dynamic_override"},
    "manual_prof": {"SOURCE": "dynamic_override_all"}
}
print(json.dumps(profiles))
"""
    (dim_path / "profiles.py").write_text(script_content)
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

def test_load_dynamic_profiles(setup_dynamic_dimension, mocker):
    """Verify loading profiles from profiles.py."""
    dim = Dimension("gcp", setup_dynamic_dimension)
    profiles = dim.get_profiles()
    assert "proj-a" in profiles
    assert "proj-b" in profiles
    assert profiles["proj-a"] == {"GCP_PROJECT": "project-a", "GCP_ZONE": "us-central1-a"}
    assert profiles["proj-b"] == {"GCP_PROJECT": "project-b", "GCP_ZONE": "europe-west1-b"}
    assert dim.get_default_profile_name() == "proj-a"

def test_profile_loading_precedence(setup_precedence_dimension, mocker):
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
    (profiles_dir / "real_prof.profile").write_text("VAR=value")
    (dim_path / "default.txt").write_text("fake_prof") # Non-existent default

    dim = Dimension("invalid_default", dim_path)
    captured = capsys.readouterr()

    assert dim.get_default_profile_name() is None # Default should be ignored
    assert "Warning: Default profile 'fake_prof'" in captured.err
    assert "not found in loaded profiles" in captured.err
    assert "real_prof" in dim.get_profiles() # The valid profile should still load


def test_invalid_yaml_format(mock_mux_dir, capsys):
    """Test behavior with incorrectly formatted profiles.yaml."""
    dim_path = mock_mux_dir / "invalid_yaml"
    dim_path.mkdir()
    # List instead of dict
    (dim_path / "profiles.yaml").write_text("- profile1: {VAR: val}")

    dim = Dimension("invalid_yaml", dim_path)
    captured = capsys.readouterr()

    assert not dim.get_profiles() # No profiles should be loaded
    # Check stderr for the warning
    assert "Warning: Invalid format in" in captured.err
    assert "Expected a top-level dictionary" in captured.err


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
    captured = capsys.readouterr()

    profiles = dim.get_profiles()
    assert "good_prof" in profiles # Good one should load
    assert "bad_prof" not in profiles # Bad one should be skipped
    # Check stderr for the warning
    assert "Warning: Invalid format for profile 'bad_prof'" in captured.err


def test_dynamic_script_error(mock_mux_dir, capsys, mocker):
    """Test behavior when profiles.py fails to execute."""
    dim_path = mock_mux_dir / "script_error"
    dim_path.mkdir()
    script_content = """
import sys
print("Something went wrong", file=sys.stderr)
sys.exit(1)
"""
    (dim_path / "profiles.py").write_text(script_content)

    dim = Dimension("script_error", dim_path)
    captured = capsys.readouterr()

    assert not dim.get_profiles()
    assert "Warning: Error executing" in captured.err
    assert "Stderr:" in captured.err
    assert "Something went wrong" in captured.err


def test_dynamic_script_invalid_json(mock_mux_dir, capsys, mocker):
    """Test behavior when profiles.py outputs invalid JSON."""
    dim_path = mock_mux_dir / "invalid_json"
    dim_path.mkdir()
    script_content = """
print("this is not json")
"""
    (dim_path / "profiles.py").write_text(script_content)

    dim = Dimension("invalid_json", dim_path)
    captured = capsys.readouterr()

    assert not dim.get_profiles()
    assert "Warning: Could not parse JSON output" in captured.err
    assert "Output was:" in captured.err
    assert "this is not json" in captured.err

def test_dynamic_script_wrong_json_structure(mock_mux_dir, capsys, mocker):
    """Test behavior when profiles.py outputs JSON but not the expected dict structure."""
    dim_path = mock_mux_dir / "wrong_json"
    dim_path.mkdir()
    script_content = """
import json
print(json.dumps(["list", "not", "dict"]))
"""
    (dim_path / "profiles.py").write_text(script_content)

    dim = Dimension("wrong_json", dim_path)
    captured = capsys.readouterr()

    assert not dim.get_profiles()
    assert "Warning: Invalid JSON structure" in captured.err
    assert "Expected a top-level dictionary" in captured.err


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
    assert "Error: Profile 'nonexistent' does not exist" in captured.err

    # Verify file content hasn't changed
    default_file = setup_manual_dimension / "default.txt"
    assert default_file.read_text() == original_default 