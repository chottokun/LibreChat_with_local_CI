from unittest.mock import MagicMock, patch
import pytest
import sys

# 1. Start patching docker.from_env
mock_docker_client = MagicMock()
patcher = patch('docker.from_env', return_value=mock_docker_client)
patcher.start()

# 2. Import main so it uses the mocked DOCKER_CLIENT
import main

@pytest.fixture(autouse=True)
def docker_client():
    """Fixture to provide the mock docker client and reset it between tests."""
    mock_docker_client.reset_mock()
    # Default behavior for mocks
    mock_docker_client.containers.run.side_effect = None
    mock_docker_client.containers.run.return_value = MagicMock()
    mock_docker_client.containers.get.side_effect = None
    mock_docker_client.containers.get.return_value = MagicMock()
    return mock_docker_client
