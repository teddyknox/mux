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

After installation, the `mux` command will be available in your path.

Commands that modify your shell environment (`switch`, `auto`) work by **outputting shell commands (like `export` and `unset`) to standard output**. To apply these changes, you must evaluate the output of these `mux` commands in your shell using `eval "$(...)"`.

**Automatic Activation (Optional):**

To automatically activate the default profile for any inactive dimensions when your shell starts, add the following line to your shell's configuration file (e.g., `~/.zshrc`, `~/.bashrc`):

```bash
# Activate mux default profiles on shell startup
eval "$(mux auto)"
```

Restart your shell or source the configuration file (e.g., `source ~/.zshrc`) for the changes to take effect.

## Configuration

1.  Create the configuration directory: `mkdir -p ~/.mux/dims`
2.  Define dimensions as subdirectories under `~/.mux/dims/`.
3.  Define profiles within each dimension using one of the methods:
    * **Files**: Create a `profiles/` subdirectory (`<dim>/profiles/`). Each `.env` file within is a profile (e.g., `<dim>/profiles/my-profile.env`).
    * **YAML**: Create a `<dim>/profiles.yaml` file with a `profiles:` key containing profile definitions.
    * **Script**: Create an executable `<dim>/profiles.py` script that outputs JSON with a `profiles:` key.
4.  (Optional) Define a source default by creating a `<dim>/default.txt` file containing the name of the default profile for that dimension.
5.  (Optional) Define sub-dimensions by creating a `dims/` subdirectory within a dimension (e.g., `<dim>/dims/<sub-dim>/`).

*See project documentation or code comments for more details on profile formats.*

## Usage

```bash
# Show current status (outputs info to stderr)
mux status

# Show environment variables for an active dimension (outputs info to stderr)
mux show <dimension_path>

# Switch profile (outputs shell commands to stdout for eval)
eval "$(mux switch <dimension_path> <profile_name>)"

# Switch profile using fzf selector (outputs shell commands to stdout for eval)
eval "$(mux switch <dimension_path>)"
eval "$(mux switch)" # Select dimension first, then profile

# Set the user-preferred default for a dimension (outputs info to stderr)
mux default <dimension_path> <profile_name>

# Automatically activate defaults for inactive dimensions (outputs shell commands to stdout for eval)
eval "$(mux auto)"

# Show help (argparse built-in)
mux --help
mux <command> --help
```

## Contributing

[Add contribution guidelines here if applicable]

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
