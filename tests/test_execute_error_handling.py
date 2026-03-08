import pytest
from unittest.mock import MagicMock, patch, ANY
import main
from main import KernelManager
from docker.errors import NotFound, APIError
from fastapi import HTTPException

@pytest.fixture
def kernel_manager():
    km = KernelManager()
    return km

def test_execute_code_http_exception_propagation(kernel_manager):
    """Test that HTTPException from get_or_create_container is propagated."""
    session_id = "test_session"
    code = "print('hello')"

    # Mock get_or_create_container to raise HTTPException (e.g., 503 capacity)
    with patch.object(kernel_manager, 'get_or_create_container', side_effect=HTTPException(status_code=503, detail="At capacity")):
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.execute_code(session_id, code)

        assert excinfo.value.status_code == 503
        assert excinfo.value.detail == "At capacity"

def test_execute_code_generic_exception_wrapping(kernel_manager):
    """Test that any generic Exception is caught and raised as 500 HTTPException."""
    session_id = "test_session"
    code = "print('hello')"

    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    # Mock _execute_in_container to raise a non-Docker, non-HTTP exception
    with patch.object(kernel_manager, '_execute_in_container', side_effect=ValueError("Unexpected error")):
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.execute_code(session_id, code)

        assert excinfo.value.status_code == 500
        assert "An internal error occurred" in excinfo.value.detail

def test_execute_code_unicode_decode_error(kernel_manager):
    """Test handling of UnicodeDecodeError when decoding container output."""
    session_id = "test_session"
    code = "print('hello')"

    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    mock_res = MagicMock()
    # Invalid UTF-8 bytes
    mock_res.output = (b"\xff\xfe\xfd", b"")
    mock_res.exit_code = 0

    with patch.object(kernel_manager, '_execute_in_container', return_value=mock_res):
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.execute_code(session_id, code)

        assert excinfo.value.status_code == 500
        # It should be caught by the generic except Exception block

def test_execute_code_malformed_output_unpacking(kernel_manager):
    """Test handling when exec_result.output doesn't have 2 elements."""
    session_id = "test_session"
    code = "print('hello')"

    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    mock_res = MagicMock()
    # Only 1 element instead of (stdout, stderr)
    mock_res.output = (b"just stdout",)
    mock_res.exit_code = 0

    with patch.object(kernel_manager, '_execute_in_container', return_value=mock_res):
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.execute_code(session_id, code)

        assert excinfo.value.status_code == 500

def test_execute_code_cleanup_called_on_all_failures(kernel_manager):
    """Ensure that the cleanup 'rm' is called regardless of the type of error."""
    session_id = "test_session"
    code = "print('hello')"

    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    # 1. Test generic Exception
    with patch.object(kernel_manager, '_execute_in_container', side_effect=RuntimeError("Oops")):
        with pytest.raises(HTTPException):
            kernel_manager.execute_code(session_id, code)

        # Verify rm was called
        mock_container.exec_run.assert_any_call(cmd=["rm", ANY])

    # Reset mock
    mock_container.exec_run.reset_mock()

    # 2. Test malformed output (ValueError during unpacking)
    mock_res = MagicMock()
    mock_res.output = (b"too", b"many", b"elements")
    with patch.object(kernel_manager, '_execute_in_container', return_value=mock_res):
        with pytest.raises(HTTPException):
            kernel_manager.execute_code(session_id, code)

        mock_container.exec_run.assert_any_call(cmd=["rm", ANY])

def test_execute_code_retry_both_fail_with_different_errors(kernel_manager):
    """Test retry logic where first fails with NotFound and second fails with something else."""
    session_id = "test_session"
    code = "print('retry')"

    mock_container1 = MagicMock()
    mock_container2 = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(side_effect=[mock_container1, mock_container2])

    # First: NotFound, Second: Generic Error
    with patch.object(kernel_manager, '_execute_in_container', side_effect=[NotFound("gone"), ValueError("crash")]) as mock_exec:
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.execute_code(session_id, code)

        assert excinfo.value.status_code == 500
        assert mock_exec.call_count == 2
        # Cleanup should happen on the second container
        mock_container2.exec_run.assert_called_with(cmd=["rm", ANY])
