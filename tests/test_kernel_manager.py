import pytest
from unittest.mock import MagicMock, patch
from main import KernelManager

def test_execute_code_success():
    manager = KernelManager()
    session_id = "test_session_id"
    code = "print('hello world')"

    # Mock container and its exec_run method
    mock_container = MagicMock()
    mock_exec_result = MagicMock()
    mock_exec_result.output = b"hello world\n"
    mock_exec_result.exit_code = 0
    mock_container.exec_run.return_value = mock_exec_result

    # Patch get_or_create_container to return our mock container
    with patch.object(KernelManager, 'get_or_create_container', return_value=mock_container):
        result = manager.execute_code(session_id, code)

    # Assertions
    assert result == {
        "stdout": "hello world\n",
        "stderr": "",
        "exit_code": 0
    }
    mock_container.exec_run.assert_called_once_with(
        cmd=["python3", "-c", code],
        workdir="/usr/src/app"
    )

def test_execute_code_empty_output():
    manager = KernelManager()
    session_id = "test_session_id"
    code = "pass"

    # Mock container and its exec_run method
    mock_container = MagicMock()
    mock_exec_result = MagicMock()
    mock_exec_result.output = None
    mock_exec_result.exit_code = 0
    mock_container.exec_run.return_value = mock_exec_result

    # Patch get_or_create_container to return our mock container
    with patch.object(KernelManager, 'get_or_create_container', return_value=mock_container):
        result = manager.execute_code(session_id, code)

    # Assertions
    assert result == {
        "stdout": "",
        "stderr": "",
        "exit_code": 0
    }

def test_execute_code_non_zero_exit_code():
    manager = KernelManager()
    session_id = "test_session_id"
    code = "exit(1)"

    # Mock container and its exec_run method
    mock_container = MagicMock()
    mock_exec_result = MagicMock()
    mock_exec_result.output = b""
    mock_exec_result.exit_code = 1
    mock_container.exec_run.return_value = mock_exec_result

    # Patch get_or_create_container to return our mock container
    with patch.object(KernelManager, 'get_or_create_container', return_value=mock_container):
        result = manager.execute_code(session_id, code)

    # Assertions
    assert result == {
        "stdout": "",
        "stderr": "",
        "exit_code": 1
    }
