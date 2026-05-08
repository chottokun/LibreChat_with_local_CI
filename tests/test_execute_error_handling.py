import pytest
from unittest.mock import MagicMock, patch, ANY
import main
from main import KernelManager
from fastapi import HTTPException
import docker

@pytest.fixture
def kernel_manager():
    km = KernelManager()
    return km

def test_execute_code_unicode_decode_error(kernel_manager):
    """Test that UnicodeDecodeError during output decoding is caught and returns 500."""
    session_id = "test_session"
    code = "print(b'\xff')" # Invalid UTF-8

    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    mock_res = MagicMock()
    mock_res.exit_code = 0
    # Provide bytes that will fail to decode as UTF-8
    mock_res.output = (b"\xff", b"")

    with patch.object(kernel_manager, '_execute_in_container', return_value=mock_res):
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.execute_code(session_id, code)

        assert excinfo.value.status_code == 500
        assert "An internal error occurred" in excinfo.value.detail

def test_execute_code_generic_exception_handling(kernel_manager):
    """Test that any generic exception is caught and returns 500."""
    session_id = "test_session"
    code = "1 + 1"

    kernel_manager.get_or_create_container = MagicMock(side_effect=RuntimeError("Unexpected error"))

    with pytest.raises(HTTPException) as excinfo:
        kernel_manager.execute_code(session_id, code)

    assert excinfo.value.status_code == 500
    assert "An internal error occurred" in excinfo.value.detail

def test_execute_code_http_exception_propagation(kernel_manager):
    """Test that HTTPException is propagated directly without being wrapped."""
    session_id = "test_session"
    code = "1 + 1"

    # Simulate max sessions reached or other 503/400 error
    kernel_manager.get_or_create_container = MagicMock(side_effect=HTTPException(status_code=503, detail="Capacity reached"))

    with pytest.raises(HTTPException) as excinfo:
        kernel_manager.execute_code(session_id, code)

    assert excinfo.value.status_code == 503
    assert "Capacity reached" in excinfo.value.detail

def test_execute_code_retry_success_uses_new_container(kernel_manager):
    """Test that retry uses the fresh container for both execution and cleanup."""
    session_id = "test_session"
    code = "print('hello')"

    mock_container_old = MagicMock()
    mock_container_new = MagicMock()

    # First call returns old, second (retry) returns new
    kernel_manager.get_or_create_container = MagicMock(side_effect=[mock_container_old, mock_container_new])

    mock_res = MagicMock()
    mock_res.exit_code = 0
    mock_res.output = (b"success", b"")

    with patch.object(kernel_manager, '_execute_in_container', side_effect=[docker.errors.NotFound("gone"), mock_res]) as mock_exec:
        kernel_manager.execute_code(session_id, code)

        # Verify retry execution used the NEW container
        assert mock_exec.call_args_list[1][0][0] == mock_container_new

        # Verify cleanup used the NEW container
        mock_container_new.exec_run.assert_called_with(cmd=["rm", ANY])
        # Old container cleanup might have been attempted if it was the one in scope,
        # but the code updates 'container' variable.
        mock_container_old.exec_run.assert_not_called()

def test_execute_code_cleanup_exception_ignored(kernel_manager):
    """Test that exceptions during cleanup are silently ignored."""
    session_id = "test_session"
    code = "1 + 1"

    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    mock_res = MagicMock()
    mock_res.exit_code = 0
    mock_res.output = (b"ok", b"")

    mock_container.exec_run.side_effect = Exception("Cleanup failed")

    with patch.object(kernel_manager, '_execute_in_container', return_value=mock_res):
        # Should NOT raise an exception
        result = kernel_manager.execute_code(session_id, code)
        assert result["stdout"] == "ok"
        mock_container.exec_run.assert_called_with(cmd=["rm", ANY])
