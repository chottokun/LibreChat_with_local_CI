import pytest
from unittest.mock import MagicMock, patch
from main import KernelManager

class TestKernelManager:
    def setup_method(self):
        # Clear active_kernels before each test
        KernelManager.active_kernels.clear()

    def test_start_new_container_success(self):
        with patch('main.DOCKER_CLIENT') as mock_docker_client:
            # Setup mock container
            mock_container = MagicMock()
            mock_container.id = "test_container_id_123"
            mock_docker_client.containers.run.return_value = mock_container

            km = KernelManager()
            session_id = "test_session_abc"

            # Execute
            container = km.start_new_container(session_id)

            # Assertions
            assert container.id == "test_container_id_123"
            assert km.active_kernels[session_id] == "test_container_id_123"

            # Verify DOCKER_CLIENT.containers.run was called with correct parameters
            mock_docker_client.containers.run.assert_called_once()
            _, kwargs = mock_docker_client.containers.run.call_args

            assert kwargs['image'] == "custom-rce-kernel:latest"
            assert kwargs['command'] == "tail -f /dev/null"
            assert kwargs['detach'] is True
            assert kwargs['remove'] is True
            assert kwargs['mem_limit'] == "512m"
            assert kwargs['nano_cpus'] == 500000000
            assert kwargs['network_disabled'] is True
            assert kwargs['name'].startswith(f"rce_{session_id}_")
