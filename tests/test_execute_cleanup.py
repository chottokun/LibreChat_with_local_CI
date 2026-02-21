import sys
from unittest.mock import MagicMock, patch, ANY

# Mock docker and fastapi before importing main
mock_docker = MagicMock()
sys.modules['docker'] = mock_docker

# Create real exception classes for the mocks to avoid TypeError during exception handling
class MockDockerError(Exception): pass
class MockAPIError(MockDockerError): pass
class MockNotFound(MockDockerError): pass

mock_docker.errors = MagicMock()
mock_docker.errors.APIError = MockAPIError
mock_docker.errors.NotFound = MockNotFound
sys.modules['docker.errors'] = mock_docker.errors

mock_fastapi = MagicMock()
sys.modules['fastapi'] = mock_fastapi
sys.modules['fastapi.security'] = MagicMock()
sys.modules['fastapi.responses'] = MagicMock()

mock_pydantic = MagicMock()
sys.modules['pydantic'] = mock_pydantic

import pytest

# Mock HTTPException
class MockHTTPException(Exception):
    def __init__(self, status_code, detail=None):
        self.status_code = status_code
        self.detail = detail

mock_fastapi.HTTPException = MockHTTPException

import main
# Ensure main uses our MockHTTPException
main.HTTPException = MockHTTPException

from main import KernelManager

def test_execute_code_cleanup_success():
    km = KernelManager()
    session_id = "test_session"
    code = "print('hello')"

    mock_container = MagicMock()
    # Mock get_or_create_container to return our mock_container
    km.get_or_create_container = MagicMock(return_value=mock_container)

    # Mock exec_run for the code execution
    mock_exec_result = MagicMock()
    mock_exec_result.output = (b"hello\n", b"")
    mock_exec_result.exit_code = 0
    mock_container.exec_run.return_value = mock_exec_result

    # Mock uuid to have a predictable filename
    with patch('uuid.uuid4') as mock_uuid:
        mock_uuid.return_value.hex = "123456"
        expected_filename = "exec_123456.py"
        expected_path = f"/usr/src/app/{expected_filename}"

        # Execute
        result = km.execute_code(session_id, code)

        # Assertions
        assert result["stdout"] == "hello\n"

        # Verify cleanup was called
        cleanup_call = None
        for call in mock_container.exec_run.call_args_list:
            if call.kwargs.get('cmd') == ["rm", expected_path]:
                cleanup_call = call
                break

        assert cleanup_call is not None, "Cleanup 'rm' command not found in exec_run calls"

def test_execute_code_cleanup_on_failure():
    km = KernelManager()
    session_id = "test_session"
    code = "print('hello')"

    mock_container = MagicMock()
    km.get_or_create_container = MagicMock(return_value=mock_container)

    # Mock exec_run to raise an exception during execution
    mock_container.exec_run.side_effect = [Exception("Execution failed"), MagicMock()]

    with patch('uuid.uuid4') as mock_uuid:
        mock_uuid.return_value.hex = "123456"
        expected_path = "/usr/src/app/exec_123456.py"

        # Execute - should raise HTTPException(500)
        with pytest.raises(main.HTTPException) as excinfo:
            km.execute_code(session_id, code)

        assert excinfo.value.status_code == 500

        # Verify cleanup was STILL called despite the exception
        cleanup_call = None
        for call in mock_container.exec_run.call_args_list:
            if call.kwargs.get('cmd') == ["rm", expected_path]:
                cleanup_call = call
                break

        assert cleanup_call is not None, "Cleanup 'rm' command not found in exec_run calls even on failure"

def test_execute_code_cleanup_on_exec_retry():
    """Test cleanup happens even if the first attempt fails with Docker error and retry is triggered."""
    km = KernelManager()
    session_id = "test_session"
    code = "print('hello')"

    mock_container1 = MagicMock()
    mock_container2 = MagicMock()

    # Mock get_or_create_container to return different containers on calls
    km.get_or_create_container = MagicMock(side_effect=[mock_container1, mock_container2])

    # First attempt fails with NotFound
    mock_container1.exec_run.side_effect = MockNotFound("Container gone")

    # Second attempt (retry) succeeds
    mock_exec_result = MagicMock()
    mock_exec_result.output = (b"hello retry\n", b"")
    mock_exec_result.exit_code = 0
    mock_container2.exec_run.return_value = mock_exec_result

    with patch('uuid.uuid4') as mock_uuid:
        mock_uuid.return_value.hex = "retry_hex"
        expected_path = "/usr/src/app/exec_retry_hex.py"

        # Execute
        result = km.execute_code(session_id, code)

        assert result["stdout"] == "hello retry\n"

        # Verify cleanup was called on the SECOND container
        cleanup_call = None
        for call in mock_container2.exec_run.call_args_list:
            if call.kwargs.get('cmd') == ["rm", expected_path]:
                cleanup_call = call
                break

        assert cleanup_call is not None, "Cleanup 'rm' command not found on the retry container"
