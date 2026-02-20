import sys
from unittest.mock import MagicMock, patch
import pytest
import docker
from fastapi import HTTPException

# We need to mock docker before importing main because main.py calls docker.from_env() at module level
mock_docker_client = MagicMock()

with patch("docker.from_env", return_value=mock_docker_client):
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
    kernel_manager.active_kernels[session_id] = mock_container

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
    kernel_manager.active_kernels[session_id] = mock_container

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
    # Use main.docker to ensure the same module is used as in main.py
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.reason = "Not Found"
    mock_container.reload.side_effect = main.docker.errors.NotFound("Gone", response=mock_response)
    kernel_manager.active_kernels[session_id] = mock_container

    # Mock start_new_container on the instance
    new_container = MagicMock()
    kernel_manager.start_new_container = MagicMock(return_value=new_container)

    # Execute
    container = kernel_manager.get_or_create_container(session_id, force_refresh=True)

    # Assert: container should be the new one created after the old one was not found
    assert container == new_container
    kernel_manager.start_new_container.assert_called_once_with(session_id)

def test_start_new_container_success(kernel_manager):
    session_id = "new_session"
    mock_container = MagicMock()
    mock_container.id = "new_container_id"
    main.DOCKER_CLIENT.containers.run.return_value = mock_container

    container = kernel_manager.start_new_container(session_id)

    assert container == mock_container
    assert kernel_manager.active_kernels[session_id] == mock_container
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
