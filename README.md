# Mux CLI

Manage and switch environment profiles across dimensions.

## Description

Mux makes it easy to configure and switch between different environment profiles (like Kubeconfigs, cloud credentials, blockchain RPCs) organized along hierarchical "dimensions".

## Installation

```bash
# Clone the repository (if you haven't already)
# git clone <your-repo-url>
# cd mux-project

# Install dependencies using Poetry
poetry install
```

## Setup (Shell Integration)

After installation, the `mux` command will be available in your path.

Commands that modify your shell environment, primarily `mux switch`, work by **outputting shell commands (like `export` and `unset`) to standard output**. To apply these changes, you must evaluate the output in your current shell.

**Automatic Activation (Directory-Based):**

To enable automatic switching of profiles based on your current directory, you can set up a shell hook. This hook will run automatically when you change directories (using `chpwd_functions` in Zsh, `PROMPT_COMMAND` in Bash, or PWD watcher in Fish) and execute the internal `mux _internal_auto_update` command.

This internal command searches upwards for a `.muxrc` file, starting in the current directory and then checking parent directories.

*   If a `.muxrc` file is found, Mux activates the profiles specified in that file, deactivating any other Mux-managed profiles for those dimensions.
*   If no `.muxrc` file is found in the directory hierarchy, Mux will generally leave the current Mux-managed environment variables as they are (as defined by environment variables like `MUX_ACTIVE_*`), unless a profile indicated by an environment variable no longer exists, in which case it will be deactivated.

Generate the appropriate hook script for your shell and add the evaluation command to your shell's configuration file (e.g., `~/.zshrc`, `~/.bashrc`, `~/.config/fish/config.fish`):

*   **For Zsh (`~/.zshrc`):**
    ```zsh
    # Mux auto hook
    eval "$(mux hook zsh)"
    ```
*   **For Bash (`~/.bashrc`):**
    ```bash
    # Mux auto hook
    eval "$(mux hook bash)"
    ```
*   **For Fish (`~/.config/fish/config.fish`):**
    ```fish
    # Mux auto hook
    mux hook fish | source
    ```

The `mux hook <shell>` command requires you to explicitly specify your shell (`bash`, `zsh`, or `fish`).

Restart your shell or source the configuration file (e.g., `source ~/.zshrc`) for the changes to take effect.

**`.muxrc` File Format:**

Create a file named `.muxrc` in a directory where you want specific Mux profiles to be active. Each line should contain a `dimension=profile` mapping:

```
# Example .muxrc
kubernetes=dev-cluster
aws=work-account
# Lines starting with # are ignored
```

## Configuration

1.  Create the configuration directory: `mkdir -p ~/.mux/dims`
2.  Define dimensions as subdirectories under `~/.mux/dims/`.
3.  Define profiles within each dimension using one of the methods:
    * **Files**: Create a `profiles/` subdirectory (`<dim>/profiles/`). Each `.env` file within is a profile (e.g., `<dim>/profiles/my-profile.env`).
    * **YAML**: Create a `<dim>/profiles.yaml` file with a `profiles:` key containing profile definitions.
    * **Script**: Create an executable `<dim>/profiles.py` script that outputs JSON with a `profiles:` key.
4.  (Optional) Define a source default by creating a `<dim>/default.txt` file containing the name of the default profile for that dimension.
5.  (Optional) Define sub-dimensions by creating a `dims/` subdirectory within a dimension (e.g., `<dim>/dims/<sub-dim>/`).

**Quick Setup**

Instead of manually creating the directory structure, you can use the `mux init` command:

```bash
# Initialize the basic directory structure
mux init

# Initialize with example dimensions and profiles
mux init --with-examples
```

The `--with-examples` flag creates sample dimensions (aws, k8s, k8s/namespace) with predefined profiles to help you get started.

*See project documentation or code comments for more details on profile formats.*

## Profile Configuration Methods

Mux provides three different ways to define profiles for a dimension, with a clear precedence order: **dynamic scripts** > **YAML files** > **individual env files**. If multiple methods are present, only the highest priority one will be used.

### Method 1: Individual Environment Files (Simple)

This is the simplest method for defining static profiles:

1. Create a `profiles/` directory inside your dimension: `mkdir -p ~/.mux/dims/<dimension>/profiles/`
2. Create a `.env` file for each profile (e.g., `~/.mux/dims/kubernetes/profiles/dev.env`)
3. Add environment variables in a simple KEY=VALUE format:

```
# ~/.mux/dims/kubernetes/profiles/dev.env
KUBECONFIG=/home/user/.kube/dev-config
K8S_NAMESPACE=default
K8S_CONTEXT=dev-cluster
```

Each file represents a separate profile, with the filename (minus the `.env` extension) becoming the profile name.

### Method 2: YAML Configuration (Structured)

For multiple profiles in a single file with a more structured format:

1. Create a `profiles.yaml` file in your dimension directory: `~/.mux/dims/<dimension>/profiles.yaml`
2. Define profiles as a mapping of profile names to environment variable dictionaries:

```yaml
# ~/.mux/dims/aws/profiles.yaml
dev:
  AWS_PROFILE: development
  AWS_REGION: us-west-2
  AWS_ACCOUNT_ID: "123456789012"

prod:
  AWS_PROFILE: production
  AWS_REGION: us-east-1
  AWS_ACCOUNT_ID: "987654321098"
```

### Method 3: Dynamic Scripts (Advanced)

For dynamic profile generation or when profiles depend on external factors:

1. Create an executable Python script at `~/.mux/dims/<dimension>/profiles.py`
2. Make it executable: `chmod +x ~/.mux/dims/<dimension>/profiles.py`
3. The script should output a JSON object to stdout with profile names as keys:

```python
#!/usr/bin/env python3
# ~/.mux/dims/blockchain/profiles.py
import json
import os

# You can query external sources, APIs, or use any logic to generate profiles
networks = {
    "mainnet": {
        "RPC_URL": "https://mainnet.infura.io/v3/" + os.environ.get("INFURA_KEY", ""),
        "CHAIN_ID": "1"
    },
    "testnet": {
        "RPC_URL": "https://goerli.infura.io/v3/" + os.environ.get("INFURA_KEY", ""),
        "CHAIN_ID": "5"
    }
}

# The script MUST output a JSON object to stdout
print(json.dumps(networks))
```

If your profile script is part of a dimension hierarchy, it receives the parent dimension's active profile name as its first argument, allowing child dimensions to adapt based on parent profiles.

### Setting a Default Profile

To define a default profile for a dimension:

1. Create a `default.txt` file in the dimension directory: `~/.mux/dims/<dimension>/default.txt`
2. Add the name of the default profile (just the name, no other content):

```
# ~/.mux/dims/kubernetes/default.txt
dev
```

Alternatively, you can use the provided command:

```bash
# Set the default profile for a dimension
mux set-default <dimension> <profile>

# Or use interactive selection with fzf
mux set-default # Select dimension and profile interactively using fzf
mux set-default <dimension> # Select profile interactively using fzf for the given dimension
```

The `set-default` command with no arguments will launch an interactive selector (using fzf) that lets you choose the dimension and profile. If you specify just the dimension, it will only prompt for the profile selection.

This default is stored in the `<dimension>/default.txt` file and is used as the source default for the dimension.

## Usage

```bash
# Initialize Mux directory structure
mux init
# Initialize with example dimensions and profiles
mux init --with-examples

# Show current status (outputs colorized tree to stderr)
mux status
# Show detailed status including all available profiles (outputs colorized tree to stderr)
mux status -v

# Show environment variables for an active dimension (outputs formatted table to stderr)
mux show <dimension_path>

# Switch profile (outputs shell commands to stdout - requires eval)
# Omitting profile_name launches fzf selector.
eval "$(mux switch <dimension_path> <profile_name>)"

# Switch profile using fzf selector (outputs shell commands to stdout - requires eval)
eval "$(mux switch <dimension_path>)" # Select profile interactively
eval "$(mux switch)" # Select dimension, then profile interactively

# Set the source default profile (writes to default.txt)
mux set-default <dimension_path> <profile_name>
# Set the source default profile using fzf selector
mux set-default # Select dimension and profile interactively
mux set-default <dimension_path> # Select profile interactively

# Generate shell hook script for auto-activation (outputs script to stdout)
mux hook <shell> # e.g., mux hook zsh

# Show help (argparse built-in)
mux --help
mux <command> --help
```

## Contributing

[Add contribution guidelines here if applicable]

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
