import sys
from unittest.mock import MagicMock, patch
import pytest
import docker

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
    mock_container.reload.side_effect = docker.errors.NotFound("Gone")
    kernel_manager.active_kernels[session_id] = mock_container

    # Mock start_new_container
    new_container = MagicMock()
    with patch.object(KernelManager, 'start_new_container', return_value=new_container) as mock_start_new:
        # Execute
        container = kernel_manager.get_or_create_container(session_id, force_refresh=True)

        # Assert
        assert container == new_container
        mock_start_new.assert_called_once_with(session_id)
