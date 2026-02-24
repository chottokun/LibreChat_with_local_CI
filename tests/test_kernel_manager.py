import sys
from unittest.mock import MagicMock, patch

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
    main.DOCKER_CLIENT.containers.list.reset_mock()
    main.DOCKER_CLIENT.containers.get.side_effect = None
    main.DOCKER_CLIENT.containers.list.side_effect = None
    main.DOCKER_CLIENT.containers.get.return_value = MagicMock()
    main.DOCKER_CLIENT.containers.list.return_value = []

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
