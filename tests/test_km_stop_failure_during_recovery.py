import pytest
import logging
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from main import KernelManager

@pytest.fixture(autouse=True)
def mock_docker_client():
    """Replace main.DOCKER_CLIENT with a MagicMock for each test using patch."""
    mock_client = MagicMock()
    with patch("main.DOCKER_CLIENT", mock_client):
        yield mock_client

@pytest.fixture
def kernel_manager():
    km = KernelManager()
    km.active_kernels = {} # Clear it for each test
    return km

def test_start_new_container_unlocked_stop_failure(kernel_manager, mock_docker_client, caplog):
    """
    Test that KernelManager.start_new_container_unlocked correctly handles a failure
    when trying to stop the container after an initial startup failure.
    Verifies the inner try-except block in the error handler (main.py:428).
    """
    session_id = "test_session_stop_fail"
    mock_container = MagicMock()
    mock_container.id = "mock_container_id_stop_fail"
    mock_docker_client.containers.run.return_value = mock_container

    # 1. Trigger the initial failure in start_new_container_unlocked
    # We'll make exec_run fail to enter the 'except Exception' block.
    mock_container.exec_run.side_effect = Exception("Initial exec failure")

    # 2. Trigger the second failure in the stop() call
    mock_container.stop.side_effect = Exception("Stop failed")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.start_new_container_unlocked(session_id)

        assert excinfo.value.status_code == 500
        assert "Failed to start sandbox" in excinfo.value.detail

        # Verify that the stop failure was logged
        assert "Failed to stop container mock_container_id_stop_fail after startup failure: Stop failed" in caplog.text

    # Verify that the session was NOT added to active_kernels
    assert session_id not in kernel_manager.active_kernels

def test_start_new_container_unlocked_stop_failure_no_id(kernel_manager, mock_docker_client, caplog):
    """
    Edge case: Test that KernelManager.start_new_container_unlocked handles stop failure
    even if the container object somehow lacks an 'id' attribute.
    """
    session_id = "test_session_stop_fail_no_id"
    # Create a mock that specifically DOES NOT have 'id' attribute
    mock_container = MagicMock()
    del mock_container.id

    mock_container.exec_run.side_effect = Exception("Initial exec failure")
    mock_container.stop.side_effect = Exception("Stop failed")
    mock_docker_client.containers.run.return_value = mock_container

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.start_new_container_unlocked(session_id)

        assert excinfo.value.status_code == 500
        # Verify that "unknown" was used as the ID in the log
        assert "Failed to stop container unknown after startup failure: Stop failed" in caplog.text
