import pytest
from unittest.mock import patch, MagicMock, call
import argparse
import sys

# Module to test
from mux import cli
from mux.config import DIMS_DIR, DEFAULTS_DIR

# --- Test print_shell_init_function ---

def test_print_shell_init_function_zsh(capsys):
    cli.print_shell_init_function("zsh")
    captured = capsys.readouterr()
    assert "# mux shell integration (zsh)" in captured.out
    assert "mux() {" in captured.out
    assert "command mux \"$@\"" in captured.out
    assert "eval \"$output\"" in captured.out
    printf_str = 'printf "%s\n" "$output"' # Construct string separately
    assert printf_str in captured.out
    # assert "local command_arg=\"${"${1:-}"}\"" in captured.out # Check arg extraction
    assert "case \"$command_arg\" in" in captured.out
    assert "switch|activate|set)" in captured.out
    assert "return $exit_code" in captured.out
    assert "}" in captured.out
    assert captured.err == ""

def test_print_shell_init_function_bash(capsys):
    cli.print_shell_init_function("bash")
    captured = capsys.readouterr()
    assert "# mux shell integration (bash)" in captured.out
    # Bash script is the same as zsh in this case
    assert "mux() {" in captured.out
    assert "command mux \"$@\"" in captured.out
    assert "eval \"$output\"" in captured.out
    printf_str = 'printf "%s\n" "$output"' # Construct string separately
    assert printf_str in captured.out
    assert "return $exit_code" in captured.out
    assert "}" in captured.out
    assert captured.err == ""

# --- Test handle_help ---

@patch('mux.cli.print') # Patch built-in print used within handle_help
@patch('argparse.ArgumentParser.print_help')
def test_handle_help(mock_print_help, mock_builtin_print):
    parser = argparse.ArgumentParser()
    cli.handle_help(parser)

    mock_print_help.assert_called_once()

    # Check that the specific help text parts are printed
    call_args_list = [c.args[0] for c in mock_builtin_print.call_args_list]
    printed_text = "\n".join(call_args_list)

    assert "\nShell Integration:" in printed_text
    assert "to your shell configuration file" in printed_text
    assert 'eval "$(mux init <your_shell_name>)"' in printed_text
    assert "\nConfiguration:" in printed_text
    assert f"Dimensions are stored in: {DIMS_DIR}" in printed_text
    assert f"User defaults are stored in: {DEFAULTS_DIR}" in printed_text

# --- Test main() argument parsing and dispatch ---

@patch('mux.cli.print_shell_init_function')
@patch.object(sys, 'argv', ['mux', 'init', 'zsh'])
def test_main_dispatch_init(mock_print_shell_func):
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 0 # Should exit cleanly
    mock_print_shell_func.assert_called_once_with('zsh')

@patch('mux.cli.Mux') # Mock the Mux class
@patch.object(sys, 'argv', ['mux', 'status'])
def test_main_dispatch_status(MockMux):
    mock_mux_instance = MockMux.return_value
    cli.main()
    MockMux.assert_called_once() # Ensure Mux was initialized
    mock_mux_instance.handle_status.assert_called_once()

@patch('mux.cli.Mux')
@patch.object(sys, 'argv', ['mux', 'switch', 'dim1', 'prof1'])
def test_main_dispatch_switch(MockMux):
    mock_mux_instance = MockMux.return_value
    cli.main()
    MockMux.assert_called_once()
    mock_mux_instance.handle_switch.assert_called_once_with('dim1', 'prof1')

@patch('mux.cli.Mux')
@patch.object(sys, 'argv', ['mux', 'show', 'dim1'])
def test_main_dispatch_show(MockMux):
    mock_mux_instance = MockMux.return_value
    cli.main()
    MockMux.assert_called_once()
    mock_mux_instance.handle_show.assert_called_once_with('dim1')

@patch('mux.cli.Mux')
@patch.object(sys, 'argv', ['mux', 'default', 'dim1', 'prof1'])
def test_main_dispatch_default(MockMux):
    mock_mux_instance = MockMux.return_value
    cli.main()
    MockMux.assert_called_once()
    mock_mux_instance.handle_default.assert_called_once_with('dim1', 'prof1')

@patch('mux.cli.handle_help')
@patch.object(sys, 'argv', ['mux', 'help'])
def test_main_dispatch_help(mock_handle_help):
    cli.main()
    # argparse calls print_help itself, so we check our custom handler
    mock_handle_help.assert_called_once()

@patch('mux.cli.handle_help')
@patch.object(sys, 'argv', ['mux'])
def test_main_dispatch_no_args(mock_handle_help):
    cli.main()
    # Should default to help
    mock_handle_help.assert_called_once()

@patch('mux.cli.handle_help')
@patch.object(sys, 'argv', ['mux', 'invalid'])
def test_main_dispatch_invalid_command(mock_handle_help):
    cli.main()
    # Should default to help
    mock_handle_help.assert_called_once()

@patch('mux.cli.Mux')
@patch('mux.cli.print_error')
@patch.object(sys, 'argv', ['mux', 'status'])
def test_main_catches_exception(mock_print_error, MockMux):
    # Make the Mux method raise an exception
    mock_mux_instance = MockMux.return_value
    test_exception = Exception("Something went wrong!")
    mock_mux_instance.handle_status.side_effect = test_exception

    with pytest.raises(SystemExit) as e:
        cli.main()

    assert e.value.code == 1 # Should exit with error code
    mock_print_error.assert_called_once()
    # Check that the error message includes the exception text
    assert str(test_exception) in mock_print_error.call_args[0][0] 