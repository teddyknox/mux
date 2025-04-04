#!/usr/bin/env python3

import os
from pathlib import Path

# Core configuration paths and constants for Mux.

# Root configuration directory (~/.mux)
MUX_DIR = Path(os.environ.get("MUX_DIR", Path.home() / ".mux"))

# Directory where dimension configurations are stored (~/.mux/dims)
DIMS_DIR = MUX_DIR / "dims"

# Directory for storing user default profile selections (~/.mux/defaults)
MUX_DEFAULT_PROFILES_DIR = MUX_DIR / "defaults"

# Filename used for source-defined default within a dimension directory
DEFAULT_FILENAME = "default.txt"

# Environment variable prefix for active profile tracking (e.g., MUX_ACTIVE_KUBE)
ENV_VAR_PREFIX = "MUX_ACTIVE"

# Suffix for environment files used in file-based profile loading
PROFILE_ENV_FILE_SUFFIX = ".env"

# Ensure base directories exist (optional, can be done on demand)
# DIMS_DIR.mkdir(parents=True, exist_ok=True)
# MUX_DEFAULT_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
