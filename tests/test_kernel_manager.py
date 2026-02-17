import pytest
from unittest.mock import MagicMock, patch
import docker

# Mock docker.from_env before importing main to avoid connection errors
with patch('docker.from_env') as mock_docker_from_env:
    import main

def test_execute_code_exception_handling(mocker):
    # km = main.KernelManager() # main already has a global instance
    km = main.kernel_manager
    session_id = "test_session"
    code = "print('hello')"

    # Mock container
    mock_container = MagicMock()
    # Mock exec_run to raise an exception
    mock_container.exec_run.side_effect = Exception("Test exception")

    # Mock get_or_create_container to return our mock container
    mocker.patch.object(km, 'get_or_create_container', return_value=mock_container)

    result = km.execute_code(session_id, code)

    assert result == {"error": "Test exception"}

def test_execute_code_success(mocker):
    km = main.kernel_manager
    session_id = "test_session"
    code = "print('hello')"

    # Mock container
    mock_container = MagicMock()
    # Mock exec_run result
    mock_exec_result = MagicMock()
    mock_exec_result.output = b"hello\n"
    mock_exec_result.exit_code = 0
    mock_container.exec_run.return_value = mock_exec_result

    # Mock get_or_create_container to return our mock container
    mocker.patch.object(km, 'get_or_create_container', return_value=mock_container)

    result = km.execute_code(session_id, code)

    assert result == {
        "stdout": "hello\n",
        "stderr": "",
        "exit_code": 0
    }
