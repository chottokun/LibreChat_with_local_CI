import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
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

def test_start_new_container_unlocked_exec_failure(kernel_manager, mock_docker_client):
    """
    Test that KernelManager.start_new_container_unlocked correctly raises a 500 HTTPException
    when the container.exec_run call fails during initialization.
    Verifies main.py:403 error handler.
    """
    session_id = "test_session"
    mock_container = MagicMock()
    mock_docker_client.containers.run.return_value = mock_container

    # Mock exec_run to raise an exception
    mock_container.exec_run.side_effect = Exception("Exec failed")

    with patch("main.logger") as mock_logger:
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.start_new_container_unlocked(session_id)

        assert excinfo.value.status_code == 500
        assert "Failed to start sandbox" in excinfo.value.detail

        # Verify exception was logged
        mock_logger.exception.assert_called_once_with(
            "Failed to start sandbox for session %s", session_id
        )

    # Verify that the session was NOT added to active_kernels (or was removed)
    assert session_id not in kernel_manager.active_kernels
