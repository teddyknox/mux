# Mux Design Doc

Mux is a tool that makes it easy to configure and switch between different environment profiles along "dimensions". A dimension is a set of profiles that are mutually exclusive, e.g. one dimension might be your Kubernetes cluster configuration, where there are many configurations. Another might be your AWS account or a blockchain connection.

## Core Concepts

### Dimensions
- A dimension represents a configuration category where only one profile can be active at a time
- Dimensions are stored as directories under `~/.mux/dims/`
- Dimensions can be hierarchical, with subdimensions stored in a `dims/` directory within their parent dimension
- Dimensions are referenced by their path, e.g., `kubernetes` or `kubernetes/namespace`

### Profiles
- Each dimension contains multiple profiles, which are mutually exclusive configurations
- Profiles define environment variables that should be set when the profile is active
- Only one profile can be active per dimension at any time

### Activation State
- The active profile for each dimension is stored in environment variables (e.g., `MUX_ACTIVE_KUBERNETES=dev`)
- Variables set by profiles are tracked in a `MUX_MANAGED_VARS_*` environment variable per dimension
- This allows each shell session to have different profiles activated

## Directory Structure

- `~/.mux/` - Root configuration directory
  - `dims/` - Contains dimension directories
    - `<dimension>/` - A dimension (e.g., `kubernetes/`)
      - `profiles/` - Directory containing profile files
        - `<profile>.env` - A profile file
      - `profiles.yaml` - Alternative way to define profiles
      - `profiles.py` - Script to dynamically generate profiles
      - `default.txt` - Defines the default profile for this dimension
      - `dims/` - Contains subdimensions
        - `<subdimension>/` - A subdimension (e.g., `namespace/`)
  - `defaults/` - User-defined defaults for dimensions

## Profile Configuration Methods

Mux supports three different ways to define profiles for a dimension, with precedence in this order:

1. **Dynamic Script**: Executable `profiles.py` script that outputs JSON
2. **YAML Configuration**: Single `profiles.yaml` file with multiple profiles 
3. **Individual Files**: Multiple `.env` files in a `profiles/` directory

### Method 1: Individual Environment Files

- Create `.env` files in the `profiles/` directory of a dimension
- Each file contains `KEY=VALUE` pairs, one per line
- Comments (lines starting with `#`) are ignored
- The filename (minus `.env` extension) becomes the profile name

### Method 2: YAML Configuration

- Create a `profiles.yaml` file in the dimension directory
- Define profiles as a mapping of profile names to environment variable dictionaries
- Each profile has environment variable names as keys and their values as values

### Method 3: Dynamic Scripts

- Create an executable `profiles.py` script in the dimension directory
- The script should output a JSON object to stdout with profile names as keys
- Each profile maps to a dictionary of environment variables
- For subdimensions, the parent dimension's active profile is passed as an argument

## State Management

- Active profiles are tracked via `MUX_ACTIVE_*` environment variables
- Variables set by profiles are tracked in `MUX_MANAGED_VARS_*` environment variables as JSON arrays
- When switching profiles:
  1. All variables managed by the old profile are unset
  2. All variables from the new profile are exported
  3. The `MUX_ACTIVE_*` variable is updated
  4. The `MUX_MANAGED_VARS_*` variable is updated

## Shell Integration

Mux includes shell integration through hook scripts that provide:

1. **Auto-activation**: Activates profiles based on `.muxrc` files when changing directories
2. **Shell Command Wrapper**: Handles evaluation of `mux switch` output

### Auto-activation with `.muxrc`

- Create a `.muxrc` file in a directory to define which profiles should be active
- Format: `dimension=profile` pairs, one per line
- Comments (lines starting with `#`) are ignored
- When changing to a directory, mux searches for `.muxrc` files in that directory and its parents
- Profiles are activated/deactivated based on the first `.muxrc` found

### Shell Hook Integration

- Add `eval "$(mux hook <shell>)"` to your shell config file
- Supported shells: bash, zsh, fish
- This adds a hook that runs when changing directories
- It also provides a `mux` wrapper function that evaluates the output of `mux switch`

## CLI Commands

`mux status`: Shows active profiles for each dimension (colorized output). Hierarchical dimensions are displayed in a tree format.

`mux status -v`: Shows all available profiles, not just active ones.

`mux switch <dim-name> <profile>`: Switches to the specified profile for the dimension, unsetting all variables from the previous profile.

`mux switch <dim-name>`: Opens an fzf UI to select which profile to activate for the dimension.

`mux switch`: Opens an fzf UI to select which dimension to switch, then an fzf UI to select which profile to switch to.

`mux show <dim-name>`: Pretty prints the environment variables currently active for that dimension.

`mux set-default <dim-name> <profile-name>`: Sets the default for the dimension to the given profile name. Updates the `default.txt` within the dimension.

`mux set-default <dim-name>`: Opens an fzf UI to select which profile to set as default.

`mux set-default`: Opens an fzf UI to select which dimension to set a default for, then an fzf UI to select which profile to set as default.

`mux default <dim-name> <profile-name>`: Sets the default profile (alternative command to `set-default`).

`mux init`: Initializes the mux directory structure.

`mux init --with-examples`: Initializes with example dimensions and profiles.

`mux hook <shell>`: Generates shell integration code for auto-activation.

`mux help`: Shows help information for commands.

## Internal Features

- **Error Handling**: Robust error handling with custom exception types
- **Environment Tracking**: Tracks which environment variables are managed by each dimension
- **Default Profiles**: Supports both source defaults (in `default.txt`) and user defaults
- **FZF Integration**: Interactive selection using fzf for dimensions and profiles
- **Consistent Shell Commands**: Generates shell commands for portability across shells

## Implementation Details

- Written in Python for simplicity and portability
- Modular design with separation of concerns:
  - `core.py`: Central orchestration and dimension management
  - `dimension.py`: Dimension and profile loading
  - `profiles.py`: Profile loading from different sources
  - `state.py`: Environment variable state management
  - `shell.py`: Shell interaction (fzf, command generation)
  - `cli.py`: Command-line interface and argument parsing
  - `prompt_scripts.py`: Shell hook scripts
  - `ui.py`: User interface (colorized output)
  - `exceptions.py`: Custom exception types
  - `config.py`: Configuration constants 