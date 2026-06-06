import pytest
import logging
import os
from unittest.mock import MagicMock, patch

# Mock docker.from_env and set env vars before importing main to prevent side effects
with patch("docker.from_env") as mock_from_env:
    os.environ.setdefault("LIBRECHAT_CODE_API_KEY", "dummy-key")
    os.environ.setdefault("DISABLE_CODE_API_AUTH", "true")
    from main import KernelManager

from fastapi import HTTPException
import docker

@pytest.fixture
def kernel_manager():
    return KernelManager()

def test_execute_code_logs_exception_on_generic_error(kernel_manager, caplog):
    """Test that KernelManager.execute_code logs the exception when a generic error occurs."""
    session_id = "test_log_session"
    code = "print('hello')"

    # Force a generic exception during container retrieval
    with patch.object(kernel_manager, 'get_or_create_container', side_effect=RuntimeError("Generic container error")):
        with caplog.at_level(logging.ERROR):
            with pytest.raises(HTTPException) as excinfo:
                kernel_manager.execute_code(session_id, code)

            assert excinfo.value.status_code == 500
            assert "An internal error occurred" in excinfo.value.detail

            # Verify logging
            assert "Error executing code in session test_log_session" in caplog.text
            # Check for the specific exception message if possible
            assert "Generic container error" in caplog.text

def test_execute_code_logs_exception_on_execution_error(kernel_manager, caplog):
    """Test that KernelManager.execute_code logs the exception when an error occurs during execution."""
    session_id = "test_exec_log_session"
    code = "print('hello')"

    mock_container = MagicMock()
    with patch.object(kernel_manager, 'get_or_create_container', return_value=mock_container):
        with patch.object(kernel_manager, '_execute_in_container', side_effect=RuntimeError("Execution failure")):
            with caplog.at_level(logging.ERROR):
                with pytest.raises(HTTPException) as excinfo:
                    kernel_manager.execute_code(session_id, code)

                assert excinfo.value.status_code == 500
                assert "Error executing code in session test_exec_log_session" in caplog.text
                assert "Execution failure" in caplog.text

def test_execute_code_logs_exception_on_retry_failure(kernel_manager, caplog):
    """Test that KernelManager.execute_code logs the exception when an error occurs during retry."""
    session_id = "test_retry_log_session"
    code = "print('hello')"

    mock_container = MagicMock()
    # First call returns container, second call (retry) returns container
    with patch.object(kernel_manager, 'get_or_create_container', return_value=mock_container):
        # First execution fails with NotFound (triggers retry), second fails with RuntimeError
        with patch.object(kernel_manager, '_execute_in_container',
                          side_effect=[docker.errors.NotFound("gone"), RuntimeError("Retry failure")]):
            with caplog.at_level(logging.ERROR):
                with pytest.raises(HTTPException) as excinfo:
                    kernel_manager.execute_code(session_id, code)

                assert excinfo.value.status_code == 500
                assert "Error executing code in session test_retry_log_session" in caplog.text
                assert "Retry failure" in caplog.text
