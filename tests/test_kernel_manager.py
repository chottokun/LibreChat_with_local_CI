import pytest
from unittest.mock import MagicMock, patch
import docker.errors
import main

class TestKernelManager:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        # Clear active_kernels before each test
        main.KernelManager.active_kernels = {}

    @patch('main.DOCKER_CLIENT')
    def test_restarts_stopped_container(self, mock_docker_client):
        manager = main.KernelManager()
        session_id = "test_session"
        container_id = "test_container_id"
        manager.active_kernels[session_id] = container_id

        mock_container = MagicMock()
        mock_container.status = "exited"
        mock_docker_client.containers.get.return_value = mock_container

        result = manager.get_or_create_container(session_id)

        mock_docker_client.containers.get.assert_called_with(container_id)
        mock_container.start.assert_called_once()
        assert result == mock_container
        assert manager.active_kernels[session_id] == container_id

    @patch('main.DOCKER_CLIENT')
    def test_returns_running_container(self, mock_docker_client):
        manager = main.KernelManager()
        session_id = "test_session"
        container_id = "test_container_id"
        manager.active_kernels[session_id] = container_id

        mock_container = MagicMock()
        mock_container.status = "running"
        mock_docker_client.containers.get.return_value = mock_container

        result = manager.get_or_create_container(session_id)

        mock_docker_client.containers.get.assert_called_with(container_id)
        mock_container.start.assert_not_called()
        assert result == mock_container

    @patch('main.DOCKER_CLIENT')
    def test_handles_missing_container(self, mock_docker_client):
        manager = main.KernelManager()
        session_id = "test_session"
        container_id = "test_container_id"
        manager.active_kernels[session_id] = container_id

        mock_docker_client.containers.get.side_effect = docker.errors.NotFound("Not Found")

        # We need to mock start_new_container since it's called after cleanup
        with patch.object(main.KernelManager, 'start_new_container') as mock_start_new:
            mock_new_container = MagicMock()
            mock_start_new.return_value = mock_new_container

            result = manager.get_or_create_container(session_id)

            assert session_id not in manager.active_kernels
            mock_start_new.assert_called_once_with(session_id)
            assert result == mock_new_container

    @patch('main.DOCKER_CLIENT')
    def test_new_session_creates_container(self, mock_docker_client):
        manager = main.KernelManager()
        session_id = "new_session"

        with patch.object(main.KernelManager, 'start_new_container') as mock_start_new:
            mock_new_container = MagicMock()
            mock_start_new.return_value = mock_new_container

            result = manager.get_or_create_container(session_id)

            mock_start_new.assert_called_once_with(session_id)
            assert result == mock_new_container
