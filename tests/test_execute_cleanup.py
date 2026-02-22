import pytest
from unittest.mock import MagicMock, patch
import main
from main import KernelManager
from docker.errors import NotFound, APIError

def test_execute_code_cleanup_success():
    km = KernelManager()
    session_id = "test_session"
    code = "print('hello')"

    mock_container = MagicMock()
    # Mock get_or_create_container to return our mock_container
    km.get_or_create_container = MagicMock(return_value=mock_container)

    # Mock _execute_in_container instead of container.exec_run
    mock_exec_result = MagicMock()
    mock_exec_result.output = (b"hello\n", b"")
    mock_exec_result.exit_code = 0

    with patch.object(km, '_execute_in_container', return_value=mock_exec_result) as mock_exec:
        # Mock uuid to have a predictable filename
        with patch('main.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value.hex = "123456"
            expected_filename = "exec_123456.py"
            expected_path = f"/mnt/data/{expected_filename}"

            # Execute
            result = km.execute_code(session_id, code)

            # Assertions
            assert result["stdout"] == "hello\n"
            mock_exec.assert_called_once()

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

    # Mock _execute_in_container to raise an exception
    with patch.object(km, '_execute_in_container', side_effect=Exception("Execution failed")):
        with patch('main.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value.hex = "123456"
            expected_path = "/mnt/data/exec_123456.py"

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

    # Second attempt (retry) succeeds
    mock_exec_result = MagicMock()
    mock_exec_result.output = (b"hello retry\n", b"")
    mock_exec_result.exit_code = 0

    # Mock _execute_in_container to fail first then succeed
    with patch.object(km, '_execute_in_container', side_effect=[NotFound("Container gone"), mock_exec_result]) as mock_exec:
        with patch('main.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value.hex = "retry_hex"
            expected_path = "/mnt/data/exec_retry_hex.py"

            # Execute
            result = km.execute_code(session_id, code)

            assert result["stdout"] == "hello retry\n"
            assert mock_exec.call_count == 2

            # Verify cleanup was called on the SECOND container (which is what execute_code ends with)
            cleanup_call = None
            for call in mock_container2.exec_run.call_args_list:
                if call.kwargs.get('cmd') == ["rm", expected_path]:
                    cleanup_call = call
                    break

            assert cleanup_call is not None, "Cleanup 'rm' command not found on the retry container"
