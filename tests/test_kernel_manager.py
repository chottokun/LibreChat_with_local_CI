import sys
import io
import tarfile
import os
from unittest.mock import MagicMock, patch, mock_open

# --- Dependency Mocking for Unit Testing ---
# We mock external libraries to ensure tests are fast, deterministic, and runnable
# even if the dependencies are not installed in the local environment.

# 1. Mock Docker
mock_docker = MagicMock()
sys.modules.setdefault("docker", mock_docker)

class DockerError(Exception): pass
class NotFound(DockerError):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response
mock_docker.errors.NotFound = NotFound

# 2. Mock FastAPI
mock_fastapi = MagicMock()
class HTTPException(Exception):
    def __init__(self, status_code, detail=None):
        self.status_code = status_code
        self.detail = detail
mock_fastapi.HTTPException = HTTPException
sys.modules.setdefault("fastapi", mock_fastapi)
sys.modules.setdefault("fastapi.security", MagicMock())
sys.modules.setdefault("fastapi.responses", MagicMock())

# 3. Mock Pydantic
class BaseModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
mock_pydantic = MagicMock()
mock_pydantic.BaseModel = BaseModel
sys.modules.setdefault("pydantic", mock_pydantic)

# --- Test Imports ---
import pytest
import time
import docker
from fastapi import HTTPException

# Mock docker.from_env before importing main
mock_docker_client = MagicMock()
mock_docker.from_env.return_value = mock_docker_client

import main
from main import KernelManager

@pytest.fixture(autouse=True)
def reset_docker_client():
    main.DOCKER_CLIENT.containers.get.reset_mock()
    main.DOCKER_CLIENT.containers.run.reset_mock()
    main.DOCKER_CLIENT.containers.get.side_effect = None
    main.DOCKER_CLIENT.containers.get.return_value = MagicMock()

@pytest.fixture
def kernel_manager():
    km = KernelManager()
    km.active_kernels = {} # Clear it for each test
    return km

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
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.reason = "Not Found"

    # Use pre-defined NotFound exception
    mock_container.reload.side_effect = NotFound("Gone", response=mock_response)

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
    kernel_manager.start_new_container_unlocked.assert_called_once_with(session_id)

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
    mock_res.output = b"file1.txt\nfile2.py\n\n"
    mock_container.exec_run.return_value = mock_res

    # Execute
    files = kernel_manager.list_files(session_id)

    # Assert
    assert files == ["file1.txt", "file2.py"]
    kernel_manager.get_or_create_container.assert_called_once_with(session_id)
    mock_container.exec_run.assert_called_once_with(cmd=["ls", "-1", "/mnt/data"])

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
    kernel_manager.get_or_create_container.assert_called_once_with(session_id)
    mock_container.exec_run.assert_called_once()

def test_upload_file_docker_mode(kernel_manager):
    # Setup
    session_id = "test_session"
    filename = "test.txt"
    content = b"hello world"
    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    with patch("main.RCE_DATA_DIR_HOST", None):
        # Execute
        kernel_manager.upload_file(session_id, filename, content)

    # Assert
    kernel_manager.get_or_create_container.assert_called_once_with(session_id)
    mock_container.put_archive.assert_called_once()
    args, _ = mock_container.put_archive.call_args
    assert args[0] == "/mnt/data"

    # Verify tar content
    tar_data = args[1]
    tar_stream = io.BytesIO(tar_data)
    with tarfile.open(fileobj=tar_stream, mode='r') as tar:
        members = tar.getmembers()
        assert len(members) == 1
        assert members[0].name == filename
        assert tar.extractfile(members[0]).read() == content

def test_upload_file_volume_mode(kernel_manager):
    # Setup
    session_id = "test_session"
    filename = "test.txt"
    content = b"hello volume"
    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("os.makedirs") as mock_makedirs, \
         patch("builtins.open", mock_open()) as m:
            # Execute
            kernel_manager.upload_file(session_id, filename, content)

            # Assert
            mock_makedirs.assert_called_once_with("/internal/path/test_session", exist_ok=True)
            m.assert_called_once_with("/internal/path/test_session/test.txt", "wb")
            m().write.assert_called_once_with(content)
            kernel_manager.get_or_create_container.assert_called_once_with(session_id)

def test_upload_file_path_traversal(kernel_manager):
    # Setup
    session_id = "test_session"
    filename = "../../../etc/passwd"
    content = b"malicious"
    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    with patch("main.RCE_DATA_DIR_HOST", None):
        # Execute
        kernel_manager.upload_file(session_id, filename, content)

    # Assert: should be sanitized to 'passwd'
    args, _ = mock_container.put_archive.call_args
    tar_data = args[1]
    tar_stream = io.BytesIO(tar_data)
    with tarfile.open(fileobj=tar_stream, mode='r') as tar:
        members = tar.getmembers()
        assert members[0].name == "passwd"

def test_upload_file_invalid_filename(kernel_manager):
    with pytest.raises(HTTPException) as excinfo:
        kernel_manager.upload_file("session1", "", b"content")
    assert excinfo.value.status_code == 400

def test_download_file_docker_mode(kernel_manager):
    # Setup
    session_id = "test_session"
    filename = "test.txt"
    content = b"download me"
    mtime = 123456789.0

    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    # Create a mock tar archive
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode='w') as tar:
        tar_info = tarfile.TarInfo(name=filename)
        tar_info.size = len(content)
        tar.addfile(tar_info, io.BytesIO(content))

    mock_container.get_archive.return_value = ([tar_stream.getvalue()], {"mtime": mtime})

    with patch("main.RCE_DATA_DIR_HOST", None):
        # Execute
        downloaded_content, downloaded_mtime = kernel_manager.download_file(session_id, filename)

    # Assert
    assert downloaded_content == content
    assert downloaded_mtime == mtime
    mock_container.get_archive.assert_called_once_with(f"/mnt/data/{filename}")

def test_download_file_volume_mode(kernel_manager):
    # Setup
    session_id = "test_session"
    filename = "test.txt"
    content = b"volume download"
    mtime = 987654321.0

    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getmtime", return_value=mtime), \
         patch("builtins.open", mock_open(read_data=content)) as m:

        # Execute
        downloaded_content, downloaded_mtime = kernel_manager.download_file(session_id, filename)

    # Assert
    assert downloaded_content == content
    assert downloaded_mtime == mtime
    m.assert_called_once_with("/internal/path/test_session/test.txt", "rb")

def test_download_file_not_found_docker(kernel_manager):
    # Setup
    session_id = "test_session"
    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)
    mock_container.get_archive.side_effect = Exception("Not found")

    with patch("main.RCE_DATA_DIR_HOST", None):
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.download_file(session_id, "missing.txt")

    assert excinfo.value.status_code == 404

def test_download_file_not_found_volume(kernel_manager):
    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("os.path.exists", return_value=False):

        with pytest.raises(FileNotFoundError):
            kernel_manager.download_file("session_id", "missing.txt")
