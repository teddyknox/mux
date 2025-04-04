import os
import pytest
from unittest.mock import MagicMock, patch

from mux.state import (
    get_active_profile_env_var,
    get_profile_var_env_name,
    get_active_profile,
    get_currently_set_vars_for_dim,
    generate_activate_commands,
    generate_deactivate_commands
)
# Mock Dimension class needed for generate commands
class MockDimension:
    def __init__(self, name, profiles):
        self.name = name
        self._profiles = profiles

    def get_env_vars(self, profile_name):
        return self._profiles.get(profile_name, {})


# --- Test Naming Functions ---

def test_get_active_profile_env_var():
    assert get_active_profile_env_var("kube") == "MUX_ACTIVE_KUBE"
    assert get_active_profile_env_var("aws_Region") == "MUX_ACTIVE_AWS_REGION"

def test_get_profile_var_env_name():
    assert get_profile_var_env_name("kube", "NAMESPACE") == "MUX_VAR_KUBE_NAMESPACE"
    assert get_profile_var_env_name("aws", "accessKeyId") == "MUX_VAR_AWS_ACCESSKEYID"

# --- Test Reading State ---

@patch.dict(os.environ, {"MUX_ACTIVE_KUBE": "dev", "MUX_ACTIVE_AWS": "prod"})
def test_get_active_profile():
    assert get_active_profile("kube") == "dev"
    assert get_active_profile("aws") == "prod"
    assert get_active_profile("gcp") is None

@patch.dict(os.environ, {
    "MUX_ACTIVE_KUBE": "dev",
    "MUX_VAR_KUBE_NAMESPACE": "dev-ns",
    "MUX_VAR_KUBE_SERVER": "https://dev.server",
    "MUX_VAR_AWS_REGION": "us-west-2",
    "OTHER_VAR": "something",
})
def test_get_currently_set_vars_for_dim():
    kube_vars = get_currently_set_vars_for_dim("kube")
    assert kube_vars == {
        "MUX_VAR_KUBE_NAMESPACE": "dev-ns",
        "MUX_VAR_KUBE_SERVER": "https://dev.server"
    }

    aws_vars = get_currently_set_vars_for_dim("aws")
    assert aws_vars == {"MUX_VAR_AWS_REGION": "us-west-2"}

    gcp_vars = get_currently_set_vars_for_dim("gcp")
    assert gcp_vars == {}

# --- Test Generating Commands ---

@patch('mux.state.get_currently_set_vars_for_dim')
def test_generate_activate_commands_no_previous(mock_get_current):
    mock_get_current.return_value = {} # No existing vars for this dim
    
    dim = MockDimension("kube", {
        "dev": {"NAMESPACE": "dev-ns", "USER": "dev-user"}
    })
    
    commands = generate_activate_commands(dim, "dev")
    
    expected = [
        # No unset commands expected
        "export MUX_VAR_KUBE_NAMESPACE='dev-ns'",
        "export MUX_VAR_KUBE_USER='dev-user'",
        "export MUX_ACTIVE_KUBE='dev'"
    ]
    assert commands == expected
    mock_get_current.assert_called_once_with("kube")

@patch('mux.state.get_currently_set_vars_for_dim')
def test_generate_activate_commands_with_previous(mock_get_current):
    mock_get_current.return_value = { # Previous profile vars
        "MUX_VAR_KUBE_NAMESPACE": "old-ns", 
        "MUX_VAR_KUBE_TOKEN": "old-token"
    }
    
    dim = MockDimension("kube", {
        "prod": {"NAMESPACE": "prod-ns", "SERVER": "prod.server"}
    })
    
    commands = generate_activate_commands(dim, "prod")
    
    expected = [
        "unset MUX_VAR_KUBE_NAMESPACE", # Unset old vars
        "unset MUX_VAR_KUBE_TOKEN",
        "export MUX_VAR_KUBE_NAMESPACE='prod-ns'", # Export new vars
        "export MUX_VAR_KUBE_SERVER='prod.server'",
        "export MUX_ACTIVE_KUBE='prod'" # Set active profile
    ]
    # Use set comparison as order of unset commands might not be guaranteed
    assert set(commands) == set(expected)
    # Ensure all expected commands are present and the structure is correct
    assert len(commands) == len(expected)
    assert commands[-1] == expected[-1] # Active profile export must be last
    assert commands[0].startswith("unset")
    assert commands[1].startswith("unset")
    assert commands[2].startswith("export")
    assert commands[3].startswith("export")

    mock_get_current.assert_called_once_with("kube")

@patch('mux.state.get_currently_set_vars_for_dim')
def test_generate_deactivate_commands(mock_get_current):
    mock_get_current.return_value = { # Vars currently set for the profile to deactivate
        "MUX_VAR_KUBE_NAMESPACE": "dev-ns", 
        "MUX_VAR_KUBE_TOKEN": "dev-token"
    }
    
    dim = MockDimension("kube", {}) # Profiles content doesn't matter for deactivate
    
    commands = generate_deactivate_commands(dim)
    
    expected = [
        "unset MUX_VAR_KUBE_NAMESPACE",
        "unset MUX_VAR_KUBE_TOKEN",
        "unset MUX_ACTIVE_KUBE"
    ]
    assert set(commands) == set(expected) # Order doesn't strictly matter
    assert len(commands) == len(expected)
    assert commands[-1] == "unset MUX_ACTIVE_KUBE"

    mock_get_current.assert_called_once_with("kube")


@patch('mux.state.get_currently_set_vars_for_dim')
def test_generate_deactivate_commands_none_active(mock_get_current):
    mock_get_current.return_value = {} # No vars currently set
    dim = MockDimension("kube", {})
    commands = generate_deactivate_commands(dim)
    expected = [
        "unset MUX_ACTIVE_KUBE"
    ]
    assert commands == expected 