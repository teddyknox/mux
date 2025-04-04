#!/usr/bin/env python3

import sys
from typing import List, Dict, Optional, TYPE_CHECKING
from rich.console import Console
from rich.tree import Tree
from rich.table import Table
from rich.text import Text

# Import necessary components
from .shell import get_active_profile_from_env # Import the function to get active profile

# Use TYPE_CHECKING to avoid circular import issues at runtime
if TYPE_CHECKING:
    from .core import Dimension


# UI functions for displaying output to the user via Rich.

# Create console instances for stdout and stderr
# Use stderr for messages so stdout can be used for 'eval '
console_err = Console(stderr=True, highlight=False)
console_out = Console(highlight=False) # Use only if direct output needed

def print_error(message: str):
    """Prints an error message to stderr."""
    console_err.print(f"[bold red]Error:[/bold red] {message}")

def print_warning(message: str):
    """Prints a warning message to stderr."""
    console_err.print(f"[bold yellow]Warning:[/bold yellow] {message}")

def print_success(message: str):
     """Prints a success message to stderr."""
     console_err.print(f"[green]{message}[/green]")

def print_info(message: str):
     """Prints an informational message to stderr."""
     console_err.print(f"[dim]{message}[/dim]")

# Recursive helper function to build the status tree
def _build_status_tree(tree: Tree, dimension: 'Dimension'):
    """Recursively builds the Rich Tree for dimensions."""
    active_profile = get_active_profile_from_env(dimension)
    effective_default = dimension.get_effective_default_profile() # Method exists

    label = Text(dimension.name)

    status_parts = []
    if active_profile:
        status_parts.append(Text.from_markup(f"[bold green]active:[/] [green]{active_profile}[/]"))
    if effective_default:
        # Only show default if it's different from active or if nothing is active
        if not active_profile or active_profile != effective_default:
             status_parts.append(Text.from_markup(f"[dim]default:[/] [dim]{effective_default}[/]"))
        elif active_profile and active_profile == effective_default:
             status_parts.append(Text.from_markup(f"[dim](default)[/]")) # Indicate active is also default

    if status_parts:
        label.append(" (")
        # Join Text objects manually with a separator
        assembled_text = Text(", ").join(status_parts)
        label.append(assembled_text) # Append the joined text
        label.append(")")

    # Add node for the current dimension
    branch = tree.add(label)

    # Recursively add children
    for child in sorted(dimension.children, key=lambda d: d.name):
        _build_status_tree(branch, child)


def display_status_tree(root_dimensions: List['Dimension']):
     """Displays the dimension status as a tree."""
     if not root_dimensions:
          print_warning("No dimensions found to display status for.")
          return

     tree = Tree("[bold cyan]Dimension Status[/bold cyan]", guide_style="dim")
     for dim in sorted(root_dimensions, key=lambda d: d.name):
         _build_status_tree(tree, dim)
     console_err.print(tree)


def display_show_table(dim_path: str, active_profile: Optional[str], env_vars: Optional[Dict[str, str]]):
     """Displays environment variables for 'mux show'."""
     if not active_profile:
          print_info(f"Dimension '{dim_path}' is not currently active.")
          return

     if not env_vars:
          print_info(f"Active profile '{active_profile}' for dimension '{dim_path}' defines no environment variables.")
          return

     table = Table(
          title=f"Environment for [cyan]{dim_path}[/] (Profile: [green]{active_profile}[/])",
          show_header=True,
          header_style="bold magenta",
          box=None, # Use a simpler box style or None
          padding=(0, 1) # Less vertical padding
     )
     table.add_column("Variable", style="dim", width=30)
     table.add_column("Value")

     for key, value in sorted(env_vars.items()):
          table.add_row(key, value)

     console_err.print(table)

