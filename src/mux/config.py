#!/usr/bin/env python3

from pathlib import Path

# Core configuration paths and constants for Mux.

# Root configuration directory (~/.multiplex)
CONFIG_DIR = Path.home() / ".multiplex"

# Directory containing dimension definitions
DIMS_DIR = CONFIG_DIR / "dims"

# Directory storing user-set default profiles
DEFAULTS_DIR = CONFIG_DIR / "defaults"

# Filename used for source-defined default within a dimension directory
DEFAULT_FILENAME = "default.txt"

# Environment variable prefix for active profile tracking (e.g., MUX_ACTIVE_KUBE)
ENV_VAR_PREFIX = "MUX_ACTIVE"

# Suffix for environment files used in file-based profile loading
PROFILE_ENV_FILE_SUFFIX = ".env"

# Ensure base directories exist (optional, can be done on demand)
# DIMS_DIR.mkdir(parents=True, exist_ok=True)
# DEFAULTS_DIR.mkdir(parents=True, exist_ok=True)

