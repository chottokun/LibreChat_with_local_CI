import pytest
from unittest.mock import MagicMock, patch
import docker
from fastapi import HTTPException
import main
from main import KernelManager
import time

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

    # Use the mock exception from conftest
    from docker.errors import NotFound
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
