import pytest
import time
import io
import tarfile
import json
from unittest.mock import MagicMock, patch, ANY
from docker.errors import NotFound
from fastapi import HTTPException
import main
from main import KernelManager

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
    km.active_kernels = {} # Clear it for each test
    return km

def test_kernel_manager_init():
    """
    KernelManager の新規インスタンス作成時に、
    初期状態（active_kernels, lock, nanoid_to_session, session_to_nanoid, file_id_map）が
    正しく空の辞書やスレッドロックオブジェクトとして構成されることを検証します。
    """
    km = KernelManager()
    assert km.active_kernels == {}
    
    # 異なる Python バージョンとの互換性を確保するため hasattr でロックインターフェースを確認
    assert hasattr(km.lock, 'acquire')
    assert hasattr(km.lock, 'release')
    assert km.nanoid_to_session == {}
    assert km.session_to_nanoid == {}
    assert km.file_id_map == {}

def test_get_or_create_container_running(kernel_manager):
    # Setup
    session_id = "test_session"
    mock_container = MagicMock()
    mock_container.status = "running"
    kernel_manager.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time()
    }

    # Execute
    container = kernel_manager.get_or_create_container(session_id)

    # Assert
    assert container == mock_container
    main.DOCKER_CLIENT.containers.get.assert_not_called()
    mock_container.reload.assert_not_called()

def test_get_or_create_container_stopped(kernel_manager):
    # Setup
    session_id = "test_session"
    mock_container = MagicMock()
    mock_container.status = "exited"
    kernel_manager.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time()
    }

    # Execute - Force refresh to hit the logic that reloads and restarts
    container = kernel_manager.get_or_create_container(session_id, force_refresh=True)

    # Assert
    assert container == mock_container
    mock_container.reload.assert_called_once()
    mock_container.start.assert_called_once()

def test_get_or_create_container_missing_during_reload(kernel_manager):
    # Setup
    session_id = "test_session"
    mock_container = MagicMock()

    # Use the real docker.errors.NotFound
    mock_container.reload.side_effect = NotFound("Gone")

    kernel_manager.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time()
    }

    # Mock start_new_container_unlocked on the instance
    new_container = MagicMock()
    kernel_manager.start_new_container_unlocked = MagicMock(return_value=new_container)

    # Execute
    container = kernel_manager.get_or_create_container(session_id, force_refresh=True)

    # Assert: container should be the new one created after the old one was not found
    assert container == new_container
    kernel_manager.start_new_container_unlocked.assert_called_once_with(session_id, None)

def test_start_new_container_success(kernel_manager):
    session_id = "new_session"
    mock_container = MagicMock()
    mock_container.id = "new_container_id"
    main.DOCKER_CLIENT.containers.run.return_value = mock_container

    container = kernel_manager.start_new_container(session_id)

    assert container == mock_container
    assert kernel_manager.active_kernels[session_id]["container"] == mock_container
    main.DOCKER_CLIENT.containers.run.assert_called_once()
    args, kwargs = main.DOCKER_CLIENT.containers.run.call_args
    assert kwargs["environment"] == {"PYTHONUNBUFFERED": "1"}

def test_start_new_container_failure(kernel_manager):
    session_id = "fail_session"
    main.DOCKER_CLIENT.containers.run.side_effect = Exception("Docker error")

    with pytest.raises(HTTPException) as excinfo:
        kernel_manager.start_new_container(session_id)

    assert excinfo.value.status_code == 500
    assert "Failed to start sandbox" in excinfo.value.detail

def test_list_files_success(kernel_manager):
    # Setup
    session_id = "test_session"
    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    # Mock ExecResult
    mock_res = MagicMock()
    mock_res.exit_code = 0
    mock_res.output = (json.dumps(["file1.txt", "file2.py"]).encode('utf-8'), b"")
    mock_container.exec_run.return_value = mock_res

    # Execute
    files = kernel_manager.list_files(session_id)

    # Assert
    assert files == ["file1.txt", "file2.py"]
    kernel_manager.get_or_create_container.assert_called_once_with(session_id, external_session_id=None)
    mock_container.exec_run.assert_called_once_with(
        cmd=["python3", "-c", "import os, json; print(json.dumps(os.listdir('/mnt/data')))"],
        demux=True
    )

def test_list_files_failure(kernel_manager):
    # Setup
    session_id = "test_session"
    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    # Mock ExecResult failure
    mock_res = MagicMock()
    mock_res.exit_code = 1
    mock_container.exec_run.return_value = mock_res

    # Execute
    files = kernel_manager.list_files(session_id)

    # Assert
    assert files == []
    kernel_manager.get_or_create_container.assert_called_once_with(session_id, external_session_id=None)
    mock_container.exec_run.assert_called_once()

def test_recover_containers_success(kernel_manager):
    # Setup
    mock_container1 = MagicMock()
    mock_container1.id = "c1"
    mock_container1.labels = {"session_id": "s1"}

    mock_container2 = MagicMock()
    mock_container2.id = "c2"
    mock_container2.labels = {"session_id": "s2"}

    main.DOCKER_CLIENT.containers.list.return_value = [mock_container1, mock_container2]

    # Execute
    kernel_manager.recover_containers()

    # Assert
    assert "s1" in kernel_manager.active_kernels
    assert "s2" in kernel_manager.active_kernels
    assert kernel_manager.active_kernels["s1"]["container"] == mock_container1
    assert kernel_manager.active_kernels["s2"]["container"] == mock_container2
    main.DOCKER_CLIENT.containers.list.assert_called_once_with(
        all=True,
        filters={"label": f"managed_by={main.RCE_MANAGED_BY_VALUE}"}
    )

def test_recover_containers_list_failure(kernel_manager):
    # Setup
    main.DOCKER_CLIENT.containers.list.side_effect = Exception("Docker API error")

    with patch("main.logger") as mock_logger:
        # Execute
        kernel_manager.recover_containers()

        # Assert
        mock_logger.error.assert_called()
        error_calls = [call for call in mock_logger.error.call_args_list if "Error during container recovery" in call.args[0]]
        assert len(error_calls) > 0
        assert "Docker API error" in str(error_calls[0].args[1])

def test_recover_containers_iteration_failure(kernel_manager):
    # Setup
    class FailingIterator:
        def __iter__(self):
            yield MagicMock()
            raise Exception("Iteration failed")

    main.DOCKER_CLIENT.containers.list.return_value = FailingIterator()

    with patch("main.logger") as mock_logger:
        # Execute
        kernel_manager.recover_containers()

        # Assert
        mock_logger.error.assert_called()
        error_calls = [call for call in mock_logger.error.call_args_list if "Error during container recovery" in call.args[0]]
        assert len(error_calls) > 0
        assert "Iteration failed" in str(error_calls[0].args[1])

def test_recover_containers_inner_failure(kernel_manager):
    # Setup
    mock_container1 = MagicMock()
    mock_container1.id = "c1"
    mock_container1.labels = {"session_id": "s1"}

    mock_container2 = MagicMock()
    mock_container2.id = "c2"
    mock_container2.labels = {"session_id": "s2"}

    main.DOCKER_CLIENT.containers.list.return_value = [mock_container1, mock_container2]

    with patch("main.logger") as mock_logger:
        # Make logger.info raise an exception for the first container recovery
        # The first call is "Scanning for existing containers to recover..."
        # The second call is "Recovered session s1 from container c1"
        mock_logger.info.side_effect = [None, Exception("Inner error"), None]

        # Execute
        kernel_manager.recover_containers()

        # Assert
        # Check that error was logged for container 1
        any_failed = any("Failed to recover container" in call.args[0] for call in mock_logger.error.call_args_list)
        assert any_failed

        # Container 2 should still be in active_kernels
        assert "s2" in kernel_manager.active_kernels

def test_recover_containers_assignment_failure(kernel_manager):
    # Setup
    mock_container1 = MagicMock()
    mock_container1.id = "c1"
    mock_container1.labels = {"session_id": "s1"}

    mock_container2 = MagicMock()
    mock_container2.id = "c2"
    mock_container2.labels = {"session_id": "s2"}

    main.DOCKER_CLIENT.containers.list.return_value = [mock_container1, mock_container2]

    with patch("main.logger") as mock_logger, patch("main.time.time") as mock_time:
        # Trigger an exception during the first container recovery.
        # time.time() is called after session_id check.
        mock_time.side_effect = [Exception("Time failure"), 123456789.0]

        # Execute
        kernel_manager.recover_containers()

        # Assert
        # Container 1 should NOT be in active_kernels because assignment failed due to time.time() exception
        assert "s1" not in kernel_manager.active_kernels

        # Error should be logged for container 1
        # The log message is: "Failed to recover container %s: %s", container.id, e
        mock_logger.error.assert_any_call("Failed to recover container %s: %s", "c1", ANY)

        # Container 2 should still be recovered successfully
        assert "s2" in kernel_manager.active_kernels
        assert kernel_manager.active_kernels["s2"]["container"] == mock_container2

def test_recover_containers_skips(kernel_manager):
    # Setup
    mock_container_no_id = MagicMock()
    mock_container_no_id.labels = {} # No session_id

    mock_container_exists = MagicMock()
    mock_container_exists.id = "exists"
    mock_container_exists.labels = {"session_id": "existing_session"}

    kernel_manager.active_kernels["existing_session"] = {"container": MagicMock()}

    main.DOCKER_CLIENT.containers.list.return_value = [mock_container_no_id, mock_container_exists]

    with patch("main.logger") as mock_logger:
        # Execute
        kernel_manager.recover_containers()

        # Assert
        # Should not have called logger.info with "Recovered"
        recovered_calls = [call for call in mock_logger.info.call_args_list if "Recovered session" in call.args[0]]
        assert len(recovered_calls) == 0

def test_recover_containers_session_id_extraction_failure(kernel_manager):
    # Setup
    mock_container = MagicMock()
    # Trigger Exception on labels.get
    mock_container.labels.get.side_effect = Exception("Label extraction failed")

    main.DOCKER_CLIENT.containers.list.return_value = [mock_container]

    with patch("main.logger") as mock_logger:
        # Execute
        kernel_manager.recover_containers()

        # Assert
        # Should catch "Error during container recovery"
        any_outer_failed = any("Error during container recovery" in call.args[0] for call in mock_logger.error.call_args_list)
        assert any_outer_failed

def test_recover_containers_double_fault(kernel_manager):
    """
    Verifies that if an error occurs during the inner recovery logging,
    the outer recovery error handler catches it.
    """
    # Setup
    mock_container = MagicMock()
    mock_container.id = "c1"
    mock_container.labels = {"session_id": "s1"}

    main.DOCKER_CLIENT.containers.list.return_value = [mock_container]

    with patch("main.logger") as mock_logger:
        # 1. Mock logger.info calls:
        # First call (line 277): "Scanning for existing containers..." -> Success (None)
        # Second call (line 294): "Recovered session..." -> Fails
        mock_logger.info.side_effect = [None, Exception("Inner recovery failed")]

        # 2. Mock logger.error calls:
        # First call (line 296): "Failed to recover container..." -> Fails (Double fault)
        # Second call (line 298): "Error during container recovery..." -> Success (None)
        mock_logger.error.side_effect = [Exception("Logger failure"), None]

        # Execute
        kernel_manager.recover_containers()

        # Assert
        # Check if the outer logger.error was called with the "Error during container recovery" message
        any_outer_failed = any("Error during container recovery" in call.args[0] for call in mock_logger.error.call_args_list)
        assert any_outer_failed

def test_download_file_invalid_filename(kernel_manager):
    with pytest.raises(HTTPException) as excinfo:
        kernel_manager.download_file("session_id", "")
    assert excinfo.value.status_code == 400

def test_download_file_volume_success(kernel_manager):
    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getmtime", return_value=123456789.0), \
         patch("builtins.open", MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=b"content")))))):

        content, mtime = kernel_manager.download_file("test_session", "test.txt")
        assert content == b"content"
        assert mtime == 123456789.0

def test_download_file_volume_not_found(kernel_manager):
    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("os.path.exists", return_value=False):

        with pytest.raises(FileNotFoundError):
            kernel_manager.download_file("test_session", "test.txt")

def test_download_file_docker_success(kernel_manager):
    session_id = "test_session"
    filename = "test.txt"
    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    # Create a real tar stream for robustness
    tar_stream = io.BytesIO()
    content = b"docker_content"
    with tarfile.open(fileobj=tar_stream, mode='w') as tar:
        tar_info = tarfile.TarInfo(name=filename)
        tar_info.size = len(content)
        tar.addfile(tar_info, io.BytesIO(content))

    # get_archive returns a generator of chunks (iterable) and a stat dict
    mock_container.get_archive.return_value = ([tar_stream.getvalue()], {"mtime": 987654321.0})

    with patch("main.RCE_DATA_DIR_HOST", None):
        res_content, mtime = kernel_manager.download_file(session_id, filename)
        assert res_content == content
        assert mtime == 987654321.0

def test_download_file_docker_not_found(kernel_manager):
    session_id = "test_session"
    filename = "test.txt"
    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    mock_container.get_archive.side_effect = Exception("Docker error")

    with patch("main.RCE_DATA_DIR_HOST", None):
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.download_file(session_id, filename)
        assert excinfo.value.status_code == 500

def test_download_file_docker_empty_tar(kernel_manager):
    session_id = "test_session"
    filename = "test.txt"
    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    # Empty tar
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode='w'):
        pass

    mock_container.get_archive.return_value = ([tar_stream.getvalue()], {"mtime": 0})

    with patch("main.RCE_DATA_DIR_HOST", None):
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.download_file(session_id, filename)
        assert excinfo.value.status_code == 404

def test_get_or_create_container_generic_exception_during_start(kernel_manager):
    # Setup
    session_id = "test_session"
    mock_container = MagicMock()
    mock_container.status = "exited"
    mock_container.start.side_effect = Exception("Generic startup error")

    kernel_manager.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time()
    }

    # Mock start_new_container_unlocked on the instance to verify session deletion
    new_container = MagicMock()
    def mock_start_new_unlocked(sid, external_session_id=None):
        assert sid == session_id
        # At this point, the old session MUST have been deleted from active_kernels
        assert session_id not in kernel_manager.active_kernels
        # Simulate its real behavior by adding the new one
        kernel_manager.active_kernels[sid] = {"container": new_container, "last_accessed": time.time()}
        return new_container

    kernel_manager.start_new_container_unlocked = MagicMock(side_effect=mock_start_new_unlocked)

    # Execute - Force refresh=True ensures we enter the block where start() is called
    container = kernel_manager.get_or_create_container(session_id, force_refresh=True)

    # Assert
    assert container == new_container
    mock_container.start.assert_called_once()
    kernel_manager.start_new_container_unlocked.assert_called_once_with(session_id, None)

def test_get_or_create_container_generic_exception_during_reload(kernel_manager):
    # Setup
    session_id = "test_session"
    mock_container = MagicMock()
    mock_container.reload.side_effect = Exception("Generic reload error")

    kernel_manager.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time()
    }

    # Mock start_new_container_unlocked on the instance to verify session deletion
    new_container = MagicMock()
    def mock_start_new_unlocked(sid, external_session_id=None):
        assert sid == session_id
        # At this point, the old session MUST have been deleted from active_kernels
        assert session_id not in kernel_manager.active_kernels
        # Simulate its real behavior by adding the new one
        kernel_manager.active_kernels[sid] = {"container": new_container, "last_accessed": time.time()}
        return new_container

    kernel_manager.start_new_container_unlocked = MagicMock(side_effect=mock_start_new_unlocked)

    # Execute - Force refresh=True ensures we enter the block where reload() is called
    container = kernel_manager.get_or_create_container(session_id, force_refresh=True)

    # Assert
    assert container == new_container
    mock_container.reload.assert_called_once()
    kernel_manager.start_new_container_unlocked.assert_called_once_with(session_id, None)
