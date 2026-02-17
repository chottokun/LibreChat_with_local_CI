import pytest
from unittest.mock import MagicMock, patch
import docker
from fastapi import HTTPException
import sys

# Mock docker.from_env before importing main to avoid errors if docker is not running
with patch("docker.from_env") as mock_from_env:
    import main
    from main import KernelManager

@pytest.fixture
def manager():
    return KernelManager()

def test_get_or_create_container_not_found(manager):
    session_id = "test_session_id"
    container_id = "non_existent_container_id"

    # Pre-populate active_kernels
    manager.active_kernels[session_id] = container_id

    # Mock DOCKER_CLIENT.containers.get to raise docker.errors.NotFound
    with patch("main.DOCKER_CLIENT") as mock_docker_client:
        mock_docker_client.containers.get.side_effect = docker.errors.NotFound("Container not found")

        # Mock start_new_container
        with patch.object(KernelManager, 'start_new_container') as mock_start_new:
            mock_new_container = MagicMock()

            # Side effect to verify that the old session_id was removed before starting a new one
            def side_effect(sid):
                assert sid not in manager.active_kernels
                return mock_new_container

            mock_start_new.side_effect = side_effect

            # This should trigger the except docker.errors.NotFound block
            container = manager.get_or_create_container(session_id)

            # Verify the flow
            mock_docker_client.containers.get.assert_called_with(container_id)
            mock_start_new.assert_called_with(session_id)
            assert container == mock_new_container

def test_get_or_create_container_stopped(manager):
    session_id = "test_session_stopped"
    container_id = "stopped_container_id"
    manager.active_kernels[session_id] = container_id

    with patch("main.DOCKER_CLIENT") as mock_docker_client:
        mock_container = MagicMock()
        mock_container.status = "exited"
        mock_docker_client.containers.get.return_value = mock_container

        container = manager.get_or_create_container(session_id)

        mock_docker_client.containers.get.assert_called_with(container_id)
        mock_container.start.assert_called_once()
        assert container == mock_container
        assert manager.active_kernels[session_id] == container_id

def test_get_or_create_container_running(manager):
    session_id = "test_session_running"
    container_id = "running_container_id"
    manager.active_kernels[session_id] = container_id

    with patch("main.DOCKER_CLIENT") as mock_docker_client:
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_docker_client.containers.get.return_value = mock_container

        container = manager.get_or_create_container(session_id)

        mock_docker_client.containers.get.assert_called_with(container_id)
        mock_container.start.assert_not_called()
        assert container == mock_container

def test_start_new_container_success(manager):
    session_id = "new_session"

    with patch("main.DOCKER_CLIENT") as mock_docker_client:
        mock_container = MagicMock()
        mock_container.id = "new_container_id"
        mock_docker_client.containers.run.return_value = mock_container

        container = manager.start_new_container(session_id)

        assert container == mock_container
        assert manager.active_kernels[session_id] == "new_container_id"
        mock_docker_client.containers.run.assert_called_once()

def test_start_new_container_failure(manager):
    session_id = "fail_session"

    with patch("main.DOCKER_CLIENT") as mock_docker_client:
        mock_docker_client.containers.run.side_effect = Exception("Docker error")

        with pytest.raises(HTTPException) as excinfo:
            manager.start_new_container(session_id)

        assert excinfo.value.status_code == 500
        assert "Failed to start sandbox" in excinfo.value.detail
