# Mux CLI

Manage and switch environment profiles across dimensions.

## Description

Mux makes it easy to configure and switch between different environment settings (like Kubeconfigs, cloud credentials, etc.) organized by "dimensions" (e.g., `kubernetes`, `aws`).

## Quick Start

1.  **Installation:**
    ```bash
    # Clone the repository (if you haven't already)
    # git clone <your-repo-url>
    # cd mux-project

    # Install dependencies using Poetry
    poetry install
    ```

2.  **Initialize Configuration:**
    Create the basic Mux setup in your home directory:
    ```bash
    mux init
    # Or initialize with examples:
    mux init --with-examples
    ```
    This creates the `~/.mux/dims/` directory where you'll define your dimensions and profiles.

3.  **Shell Integration (Essential for `switch`):**
    Commands like `mux switch` work by printing shell commands (`export`, `unset`). To make them affect your current shell, you **must** evaluate their output.

    Add the Mux hook to your shell configuration file (`~/.zshrc`, `~/.bashrc`, `~/.config/fish/config.fish`):

    *   **Zsh:** `eval "$(mux hook zsh)"`
    *   **Bash:** `eval "$(mux hook bash)"`
    *   **Fish:** `mux hook fish | source`

    Restart your shell or source your config file (e.g., `source ~/.zshrc`). This also enables **automatic profile switching** based on `.muxrc` files in your project directories.

4.  **Basic Usage:**
    *   **See current status:** `mux status`
    *   **Select profiles interactively:** `mux switch` (Uses `fzf`. The hook will apply changes on the next prompt/directory change.)
    *   **Select a specific profile:** `mux switch <dimension_path> <profile_name>` (e.g., `mux switch kubernetes dev-cluster`. The hook applies the change.)
    *   **Set the default profile for a dimension:**
        *   `mux set-default <dimension_path> <profile_name>` (Sets the default directly)
        *   `mux set-default` (Select dimension and profile interactively using `fzf`)
        *(This command updates the dimension's `default.txt` file.)*

## Core Concepts

*   **Dimensions:** Categories for your profiles (e.g., `kubernetes`, `aws`, `gcp`). Defined as directories under `~/.mux/dims/`. Dimensions can be nested (e.g., `kubernetes/cluster-a`).
*   **Profiles:** Specific configurations within a dimension (e.g., `dev-cluster`, `prod-account`). Defined by environment variables.
*   **`.muxrc` Files:** Place a `.muxrc` file in a project directory to automatically activate specific dimension profiles when you `cd` into it. Example:
    ```
    # project/.muxrc
    kubernetes=dev-cluster
    aws=work-account
    ```

## Configuration Overview

*   **Profiles:** Defined inside dimension directories (`~/.mux/dims/<dimension>/`).
    *(Mux uses the first method it finds in the order: script > YAML > .env files)*
    Mux supports:
    *   Simple `.env` files in a `profiles/` subdirectory (e.g., `profiles/dev.env`).
        Example `~/.mux/dims/kubernetes/profiles/dev.env`:
        ```dotenv
        # Comments are allowed
        KUBECONFIG=~/.kube/config-dev
        K8S_NAMESPACE=development
        K8S_CONTEXT=dev-cluster
        ```
    *   A single `profiles.yaml` file listing multiple profiles.
        Example `~/.mux/dims/aws/profiles.yaml`:
        ```yaml
        dev:
          AWS_PROFILE: development
          AWS_REGION: us-west-2
          AWS_ACCOUNT_ID: "123456789012"

        prod:
          AWS_PROFILE: production
          AWS_REGION: us-east-1
          AWS_ACCOUNT_ID: "987654321098"
        ```
    *   An executable `profiles.py` script for dynamic generation (outputs JSON).
        Example `~/.mux/dims/blockchain/profiles.py`:
        ```python
        #!/usr/bin/env python3
        import json
        import os

        # Example: Generate profiles dynamically
        networks = {
            "mainnet": {
                "RPC_URL": "https://mainnet.infura.io/v3/" + os.environ.get("INFURA_KEY", ""),
                "CHAIN_ID": "1"
            },
            "sepolia": {
                "RPC_URL": "https://sepolia.infura.io/v3/" + os.environ.get("INFURA_KEY", ""),
                "CHAIN_ID": "11155111"
            }
        }

        # The script MUST output a JSON object to stdout
        print(json.dumps(networks))
        ```
        *(Remember to make the script executable: `chmod +x ~/.mux/dims/blockchain/profiles.py`)*
*   **Default Profile:** Set a default profile for a dimension using `mux set-default <dimension> <profile>` or interactively with `mux set-default`. This creates a `default.txt` file.

*For detailed configuration options and advanced usage, please refer to the project documentation or code comments.*

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
