import os
import json # Added for MUX_MANAGED_VARS
from unittest.mock import MagicMock, patch
from typing import Dict, List, Optional

import pytest # Import pytest for raises

from mux.state import (
    get_active_profile_env_var,
    # get_profile_var_env_name, # No longer needed?
    get_managed_vars_env_var, # New tracker var
    get_active_profile,
    # get_currently_set_vars_for_dim, # Removed function
    get_currently_managed_vars,
    generate_activate_commands,
    generate_deactivate_commands,
)
from mux.dimension import Dimension # Import Dimension for type hint
from mux.exceptions import MuxError # Import MuxError
from mux.utils import MUX_DIR_PATH # Import for default profile tests

# Fixture for a mock Dimension object
@pytest.fixture
def mock_dimension():
    dim = MagicMock(spec=Dimension)
    dim.name = "kube"
    # Mock the method that returns profile environment variables
    dim.get_env_vars.side_effect = lambda profile_name: {"VAR1": f"{profile_name}_val1", "VAR2": f"{profile_name}_val2"} if profile_name == "dev" else {"VAR_X": "prod_valX"}
    return dim

# --- Test Reading State ---

@patch.dict(os.environ, {"MUX_ACTIVE_KUBE": "dev", "MUX_ACTIVE_AWS": "prod"})
def test_get_active_profile():
    assert get_active_profile("kube") == "dev"
    assert get_active_profile("aws") == "prod"
    assert get_active_profile("gcp") is None

# --- Test Generating Commands ---

@patch('mux.state.get_currently_managed_vars')
def test_generate_activate_commands_no_previous(mock_get_managed, mock_dimension):
    """Test activating a profile when none was active before."""
    mock_get_managed.return_value = [] # Simulate no previously managed vars

    commands = generate_activate_commands(mock_dimension, "dev")

    # Expected commands:
    # 1. Export new vars
    # 2. Export managed vars tracker
    # 3. Export active profile marker
    assert "export VAR1='dev_val1'" in commands
    assert "export VAR2='dev_val2'" in commands
    assert "unset MUX_MANAGED_VARS_KUBE" not in commands # Should set, not unset
    # Check for the export of the managed vars JSON list
    expected_managed_json = json.dumps(["VAR1", "VAR2"])
    assert f"export MUX_MANAGED_VARS_KUBE='{expected_managed_json}'" in commands
    assert "export MUX_ACTIVE_KUBE='dev'" in commands
    assert len(commands) == 4 # Ensure no extra commands

@patch('mux.state.get_currently_managed_vars')
def test_generate_activate_commands_with_previous(mock_get_managed, mock_dimension):
    """Test activating a profile when another was active."""
    # Simulate that 'VAR_OLD' and 'VAR1' were managed by the previous profile
    mock_get_managed.return_value = ["VAR_OLD", "VAR1"]

    # Activate 'dev' profile (vars: VAR1, VAR2)
    commands = generate_activate_commands(mock_dimension, "dev")

    # Expected commands:
    # 1. Unset old managed vars (VAR_OLD, VAR1)
    # 2. Export new vars (VAR1, VAR2)
    # 3. Export new managed vars tracker ([VAR1, VAR2])
    # 4. Export active profile marker (dev)

    # Check order roughly - unsets should generally come first
    unset_old_index = commands.index("unset VAR_OLD")
    unset_var1_index = commands.index("unset VAR1")
    export_var1_index = commands.index("export VAR1='dev_val1'")
    export_var2_index = commands.index("export VAR2='dev_val2'")
    export_managed_index = commands.index(f"export MUX_MANAGED_VARS_KUBE='{json.dumps(['VAR1', 'VAR2'])}'")
    export_active_index = commands.index("export MUX_ACTIVE_KUBE='dev'")

    assert unset_old_index < export_var1_index
    assert unset_var1_index < export_var1_index
    assert unset_old_index < export_var2_index
    assert unset_var1_index < export_var2_index

    assert "unset VAR_OLD" in commands
    assert "unset VAR1" in commands
    assert "export VAR1='dev_val1'" in commands
    assert "export VAR2='dev_val2'" in commands
    assert f"export MUX_MANAGED_VARS_KUBE='{json.dumps(['VAR1', 'VAR2'])}'" in commands
    assert "export MUX_ACTIVE_KUBE='dev'" in commands
    assert len(commands) == 6

@patch('mux.state.get_currently_managed_vars')
def test_generate_deactivate_commands(mock_get_managed, mock_dimension):
    """Test deactivating a profile."""
    # Simulate that 'VAR1' and 'VAR2' were managed by the active profile
    mock_get_managed.return_value = ["VAR1", "VAR2"]

    commands = generate_deactivate_commands(mock_dimension)

    # Expected commands:
    # 1. Unset managed vars (VAR1, VAR2)
    # 2. Unset managed vars tracker
    # 3. Unset active profile marker

    assert "unset VAR1" in commands
    assert "unset VAR2" in commands
    assert "unset MUX_MANAGED_VARS_KUBE" in commands
    assert "unset MUX_ACTIVE_KUBE" in commands
    assert len(commands) == 4

@patch('mux.state.get_currently_managed_vars')
def test_generate_deactivate_commands_none_active(mock_get_managed, mock_dimension):
    """Test deactivating when no profile was technically active (no managed vars tracked)."""
    mock_get_managed.return_value = [] # Simulate no managed vars tracked

    commands = generate_deactivate_commands(mock_dimension)

    # Expected commands:
    # 1. Unset managed vars tracker (even if it wasn't set, safe to unset)
    # 2. Unset active profile marker (even if it wasn't set, safe to unset)
    assert "unset MUX_MANAGED_VARS_KUBE" in commands
    assert "unset MUX_ACTIVE_KUBE" in commands
    assert len(commands) == 2 # Only unset the tracker and active vars 