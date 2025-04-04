# Mux CLI

Manage and switch environment profiles across dimensions.

## Description

Mux makes it easy to configure and switch between different environment profiles (like Kubeconfigs, cloud credentials, blockchain RPCs) organized along hierarchical "dimensions".

## Installation

```bash
# Clone the repository (if you haven't already)
# git clone <your-repo-url>
# cd mux-project

# Install using pip (in editable mode for development)
pip install -e .

# Or for regular installation:
# pip install .
```

## Setup (Shell Integration)

To enable automatic environment switching, you need to add a line to your shell's configuration file (e.g., `~/.zshrc`, `~/.bashrc`).

Run `mux init <your_shell_name>` (e.g., `mux init zsh`) and add the output to your shell configuration file:

```bash
# Example for .zshrc or .bashrc
eval "$(mux init zsh)" # Or 'bash'
```

Restart your shell or source the configuration file (`source ~/.zshrc`) for the changes to take effect. This defines a `mux` shell function that handles environment updates.

## Configuration

1.  Create the configuration directory: `mkdir -p ~/.multiplex/dims`
2.  Define dimensions as subdirectories under `~/.multiplex/dims/`.
3.  Define profiles within each dimension using one of the methods:
    * **Files**: Create a `profiles/` subdirectory (`<dim>/profiles/`). Each `.env` file within is a profile (e.g., `<dim>/profiles/my-profile.env`).
    * **YAML**: Create a `<dim>/profiles.yaml` file with a `profiles:` key containing profile definitions.
    * **Script**: Create an executable `<dim>/profiles.py` script that outputs JSON with a `profiles:` key.
4.  (Optional) Define a source default by creating a `<dim>/default.txt` file containing the name of the default profile for that dimension.
5.  (Optional) Define sub-dimensions by creating a `dims/` subdirectory within a dimension (e.g., `<dim>/dims/<sub-dim>/`).

*See project documentation or code comments for more details on profile formats.*

## Usage

After setting up shell integration, you can use `mux` commands directly:

```bash
# Show current status (outputs to stderr)
mux status

# Show environment variables for an active dimension (outputs to stderr)
mux show <dimension_path>

# Switch profile (environment updates automatically)
mux switch <dimension_path> <profile_name>

# Switch profile using fzf selector (environment updates automatically)
mux switch <dimension_path>
mux switch # Select dimension first, then profile

# Set the user-preferred default for a dimension (outputs to stderr)
mux default <dimension_path> <profile_name>

# Show help (outputs to stderr)
mux help

# Print the shell initialization script again (outputs to stdout)
mux init <shell_name>
```

## Contributing

[Add contribution guidelines here if applicable]

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
