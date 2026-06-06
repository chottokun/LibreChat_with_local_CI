import pytest
from unittest.mock import MagicMock, patch
from main import KernelManager
import main

@pytest.fixture(autouse=True)
def mock_docker_client():
    """Replace main.DOCKER_CLIENT with a MagicMock for each test."""
    mock_client = MagicMock()
    original = main.DOCKER_CLIENT
    main.DOCKER_CLIENT = mock_client
    yield mock_client
    main.DOCKER_CLIENT = original

@pytest.fixture
def kernel_manager():
    km = KernelManager()
    km.active_kernels = {}
    return km

def test_list_files_json_parse_error_fallback(kernel_manager):
    """
    Verifies that if the JSON parsing of the file list output fails,
    the method logs an error and falls back to splitting the output by lines.
    """
    # Setup
    session_id = "test_session"
    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    # Mock ExecResult with invalid JSON output
    # This should trigger the JSONDecodeError when json.loads(output) is called
    invalid_json_output = "file1.txt\nfile2.py\n"
    mock_res = MagicMock()
    mock_res.exit_code = 0
    mock_res.output = (invalid_json_output.encode('utf-8'), b"")
    mock_container.exec_run.return_value = mock_res

    with patch("main.logger") as mock_logger:
        # Execute
        files = kernel_manager.list_files(session_id)

        # Assert
        # Fallback logic at L574: files = output.splitlines()
        # and L575: return [f for f in files if f]
        assert files == ["file1.txt", "file2.py"]

        # Verify logger.error was called with the expected message
        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args[0]
        assert "Failed to parse file list JSON from container" in call_args[0]
        # Verify that both the exception and the raw output are passed to the logger
        assert invalid_json_output in call_args
