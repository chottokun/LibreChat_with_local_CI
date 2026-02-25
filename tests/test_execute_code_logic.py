import pytest
from unittest.mock import MagicMock, patch, ANY
import main
from main import KernelManager
from docker.errors import NotFound, APIError
import io
import tarfile

@pytest.fixture
def kernel_manager():
    km = KernelManager()
    return km

def test_execute_code_happy_path(kernel_manager):
    session_id = "test_session"
    code = "1 + 1"

    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    mock_res = MagicMock()
    mock_res.exit_code = 0
    mock_res.output = (b"2\n", b"")

    with patch.object(kernel_manager, '_execute_in_container', return_value=mock_res) as mock_exec:
        with patch('main.wrap_code', return_value="print(repr(1 + 1))") as mock_wrap:
            result = kernel_manager.execute_code(session_id, code)

            assert result["stdout"] == "2\n"
            assert result["stderr"] == ""
            assert result["exit_code"] == 0

            mock_wrap.assert_called_once_with(code)
            mock_exec.assert_called_once()
            # Verify cleanup
            mock_container.exec_run.assert_called_with(cmd=["rm", ANY])

def test_execute_code_retry_on_not_found(kernel_manager):
    session_id = "test_session"
    code = "print('retry')"

    mock_container1 = MagicMock()
    mock_container2 = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(side_effect=[mock_container1, mock_container2])

    mock_res = MagicMock()
    mock_res.exit_code = 0
    mock_res.output = (b"retry success\n", b"")

    # First call to _execute_in_container fails with NotFound
    # Second call (retry) succeeds
    with patch.object(kernel_manager, '_execute_in_container', side_effect=[NotFound("gone"), mock_res]) as mock_exec:
        result = kernel_manager.execute_code(session_id, code)

        assert result["stdout"] == "retry success\n"
        assert mock_exec.call_count == 2

        # Verify get_or_create_container was called with force_refresh=True for retry
        kernel_manager.get_or_create_container.assert_any_call(session_id, force_refresh=True)

        # Verify cleanup on second container
        mock_container2.exec_run.assert_called_with(cmd=["rm", ANY])

def test_execute_code_retry_on_api_error(kernel_manager):
    session_id = "test_session"
    code = "print('retry api')"

    mock_container1 = MagicMock()
    mock_container2 = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(side_effect=[mock_container1, mock_container2])

    mock_res = MagicMock()
    mock_res.exit_code = 0
    mock_res.output = (b"api retry success\n", b"")

    with patch.object(kernel_manager, '_execute_in_container', side_effect=[APIError("error"), mock_res]) as mock_exec:
        result = kernel_manager.execute_code(session_id, code)

        assert result["stdout"] == "api retry success\n"
        assert mock_exec.call_count == 2

        # Verify cleanup on second container
        mock_container2.exec_run.assert_called_with(cmd=["rm", ANY])

def test_execute_code_exhausted_retry(kernel_manager):
    session_id = "test_session"
    code = "print('fail')"

    mock_container1 = MagicMock()
    mock_container2 = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(side_effect=[mock_container1, mock_container2])

    # Both attempts fail
    with patch.object(kernel_manager, '_execute_in_container', side_effect=[NotFound("gone"), NotFound("still gone")]) as mock_exec:
        with pytest.raises(main.HTTPException) as excinfo:
            kernel_manager.execute_code(session_id, code)

        assert excinfo.value.status_code == 500
        assert mock_exec.call_count == 2

        # Verify cleanup on second container
        mock_container2.exec_run.assert_called_with(cmd=["rm", ANY])

def test_execute_in_container_logic(kernel_manager):
    mock_container = MagicMock()
    code_content = "print('hello')"
    path = "/mnt/data/exec_123.py"
    filename = "exec_123.py"

    mock_res = MagicMock()
    mock_container.exec_run.return_value = mock_res

    res = kernel_manager._execute_in_container(mock_container, code_content, path, filename)

    assert res == mock_res

    # Verify put_archive was called
    mock_container.put_archive.assert_called_once()
    args, _ = mock_container.put_archive.call_args
    assert args[0] == "/mnt/data"

    # Verify the content of the tar
    tar_data = args[1]
    with tarfile.open(fileobj=io.BytesIO(tar_data), mode='r') as tar:
        member = tar.getmember(filename)
        assert member.size == len(code_content.encode('utf-8'))
        f = tar.extractfile(member)
        assert f.read().decode('utf-8') == code_content

    # Verify exec_run was called with correct arguments
    mock_container.exec_run.assert_called_once_with(
        cmd=["python3", path],
        workdir="/mnt/data",
        demux=True
    )
