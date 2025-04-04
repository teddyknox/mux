import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from mux.cli import (
    handle_status,
    handle_init,
    # Add other functions as you develop tests for them
)

@patch('mux.cli.console.print')
@patch('mux.cli.ensure_mux_dir_exists')
@patch('mux.cli.DIMS_DIR')
@patch('mux.cli.MUX_DIR')
def test_handle_init_basic(mock_mux_dir, mock_dims_dir, mock_ensure_mux, mock_console_print):
    """Test basic init without examples creates the required directories."""
    # Setup mock paths to return themselves when used in Path operations
    mock_dims_dir.mkdir = MagicMock()
    
    # Set string representations for reporting
    mock_mux_dir.__str__.return_value = "/mock/.mux"
    mock_dims_dir.__str__.return_value = "/mock/.mux/dims"
    
    # Call with no examples
    args = MagicMock()
    args.with_examples = False
    handle_init(args)
    
    # Verify directory creation
    mock_ensure_mux.assert_called_once()
    mock_dims_dir.mkdir.assert_called_once_with(exist_ok=True)
    
    # Verify console output
    assert mock_console_print.call_count >= 3  # At least 3 calls for created directories
    
    # Verify correct directories were reported in output
    creation_messages = [call_args[0][0] for call_args in mock_console_print.call_args_list]
    mux_dir_message = next((msg for msg in creation_messages if str(mock_mux_dir) in msg), None)
    dims_dir_message = next((msg for msg in creation_messages if str(mock_dims_dir) in msg), None)
    
    assert mux_dir_message is not None
    assert dims_dir_message is not None
    
    # Verify next steps were included
    next_steps_message = next((msg for msg in creation_messages if "Next steps" in msg), None)
    assert next_steps_message is not None

@patch('mux.cli.console.print')
@patch('mux.cli.ensure_mux_dir_exists')
@patch('builtins.open', new_callable=MagicMock)
@patch('mux.cli.DIMS_DIR')
@patch('mux.cli.MUX_DIR')
def test_handle_init_with_examples(mock_mux_dir, mock_dims_dir, 
                                 mock_open, mock_ensure_mux, mock_console_print):
    """Test init with examples creates example dimensions and profiles."""
    # Set up directory structure mocks
    aws_dir = MagicMock()
    aws_profiles_dir = MagicMock()
    k8s_dir = MagicMock()
    k8s_dims_dir = MagicMock()
    namespace_dir = MagicMock()
    
    # Create mock for DIMS_DIR / "aws"
    mock_dims_dir.__truediv__.return_value = aws_dir
    aws_dir.__truediv__.side_effect = lambda x: aws_profiles_dir if x == "profiles" else k8s_dir if x == "k8s" else MagicMock()
    
    # Make mock_open return a proper context manager
    mock_file = MagicMock()
    mock_open.return_value.__enter__.return_value = mock_file
    
    # Call with examples
    args = MagicMock()
    args.with_examples = True
    handle_init(args)
    
    # Verify directory creation
    mock_ensure_mux.assert_called_once()
    
    # Verify console output for examples
    examples_mentioned = any("example dimensions" in str(call) for call in mock_console_print.call_args_list)
    assert examples_mentioned, "Example dimensions should be mentioned in output"
    
    # Verify AWS profiles created
    aws_mentioned = any("aws" in str(call) for call in mock_console_print.call_args_list)
    assert aws_mentioned, "AWS example should be mentioned in console output" 