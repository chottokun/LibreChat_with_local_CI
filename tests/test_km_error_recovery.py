import pytest
import time
from unittest.mock import MagicMock
import docker.errors
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

def test_get_or_create_container_running_with_force_refresh(kernel_manager):
    """Test line 201-202: container is running during force refresh."""
    session_id = "test_session"
    mock_container = MagicMock()
    mock_container.status = "running"

    kernel_manager.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time() - 100
    }

    # Execute with force_refresh=True
    container = kernel_manager.get_or_create_container(session_id, force_refresh=True)

    # Assert
    assert container == mock_container
    mock_container.reload.assert_called_once()
    assert kernel_manager.active_kernels[session_id]["last_accessed"] > time.time() - 5

def test_get_or_create_container_not_found_during_reload(kernel_manager, mock_docker_client):
    """Test line 195-198: NotFound during reload starts fresh."""
    session_id = "test_session"
    mock_container = MagicMock()
    # Mock NotFound during reload
    mock_container.reload.side_effect = docker.errors.NotFound("Gone")

    kernel_manager.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time()
    }

    # Mock Docker Client to return a new container
    new_container = MagicMock()
    mock_docker_client.containers.run.return_value = new_container

    # Execute
    container = kernel_manager.get_or_create_container(session_id, force_refresh=True)

    # Assert
    assert container == new_container
    # Verify it started fresh
    mock_docker_client.containers.run.assert_called_once()
    # Check that it's back in active_kernels
    assert kernel_manager.active_kernels[session_id]["container"] == new_container

def test_get_or_create_container_generic_exception_during_reload(kernel_manager, mock_docker_client):
    """Test line 208-212: generic Exception during reload starts fresh."""
    session_id = "test_session"
    mock_container = MagicMock()
    # Mock a generic Exception during reload
    mock_container.reload.side_effect = Exception("Unknown docker error")

    kernel_manager.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time()
    }

    # Mock Docker Client to return a new container
    new_container = MagicMock()
    mock_docker_client.containers.run.return_value = new_container

    # Execute
    container = kernel_manager.get_or_create_container(session_id, force_refresh=True)

    # Assert
    assert container == new_container
    # Verify it started fresh
    mock_docker_client.containers.run.assert_called_once()
    # Check that it's back in active_kernels
    assert kernel_manager.active_kernels[session_id]["container"] == new_container

def test_get_or_create_container_exception_during_start(kernel_manager, mock_docker_client):
    """Test line 208-212: Exception during start() starts fresh."""
    session_id = "test_session"
    mock_container = MagicMock()
    mock_container.status = "exited"
    mock_container.start.side_effect = Exception("Failed to start")

    kernel_manager.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time()
    }

    # Mock Docker Client to return a new container
    new_container = MagicMock()
    mock_docker_client.containers.run.return_value = new_container

    # Execute
    container = kernel_manager.get_or_create_container(session_id, force_refresh=True)

    # Assert
    assert container == new_container
    mock_docker_client.containers.run.assert_called_once()
    assert kernel_manager.active_kernels[session_id]["container"] == new_container

def test_get_or_create_container_new_session(kernel_manager, mock_docker_client):
    """Test the final return path when session is not in active_kernels."""
    session_id = "completely_new_session"

    # Mock Docker Client to return a new container
    new_container = MagicMock()
    mock_docker_client.containers.run.return_value = new_container

    # Execute
    container = kernel_manager.get_or_create_container(session_id)

    # Assert
    assert container == new_container
    mock_docker_client.containers.run.assert_called_once()
    assert kernel_manager.active_kernels[session_id]["container"] == new_container
