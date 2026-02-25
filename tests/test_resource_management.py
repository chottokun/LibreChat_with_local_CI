import time
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
import main
from main import KernelManager

@pytest.fixture(autouse=True)
def cleanup_mocks():
    """Reset the DOCKER_CLIENT mock before each test."""
    mock_docker_client = MagicMock()
    main.DOCKER_CLIENT = mock_docker_client
    yield mock_docker_client

@pytest.fixture
def km():
    manager = KernelManager()
    manager.active_kernels = {}
    return manager

def test_session_ttl_cleanup(km):
    # Setup
    session_id = "old_session"
    mock_container = MagicMock()
    km.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time() - 4000 # Older than 3600s TTL
    }

    # Execute
    km.cleanup_sessions()

    # Assert
    assert session_id not in km.active_kernels
    mock_container.stop.assert_called_once()

def test_session_limit_enforcement(km):
    # Setup: Fill up to max sessions
    with patch("main.RCE_MAX_SESSIONS", 2):
        km.active_kernels["s1"] = {"container": MagicMock(), "last_accessed": time.time()}
        km.active_kernels["s2"] = {"container": MagicMock(), "last_accessed": time.time()}

        # Execute & Assert
        with pytest.raises(HTTPException) as excinfo:
            km.start_new_container("s3")

        assert excinfo.value.status_code == 503
        assert "Server is at capacity" in excinfo.value.detail

def test_container_recovery(km, cleanup_mocks):
    # Setup
    mock_docker_client = cleanup_mocks
    mock_container = MagicMock()
    mock_container.labels = {"session_id": "recovered_session"}
    mock_container.status = "exited"
    mock_container.id = "cont_id"
    mock_docker_client.containers.list.return_value = [mock_container]

    # Execute
    km.recover_containers()

    # Assert
    assert "recovered_session" in km.active_kernels
    assert km.active_kernels["recovered_session"]["container"] == mock_container
    # We no longer auto-start during recovery to avoid load spikes
    mock_container.start.assert_not_called()

def test_get_or_create_updates_timestamp(km):
    # Setup
    session_id = "active_session"
    initial_time = time.time() - 100
    mock_container = MagicMock()
    mock_container.status = "running"
    km.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": initial_time
    }

    # Execute
    km.get_or_create_container(session_id)

    # Assert
    assert km.active_kernels[session_id]["last_accessed"] > initial_time

def test_start_new_container_adds_labels(km, cleanup_mocks):
    # Setup
    mock_docker_client = cleanup_mocks
    session_id = "labeled_session"
    mock_docker_client.containers.run.return_value = MagicMock()

    # Execute
    km.start_new_container(session_id)

    # Assert
    args, kwargs = mock_docker_client.containers.run.call_args
    assert "labels" in kwargs
    assert kwargs["labels"]["managed_by"] == main.RCE_MANAGED_BY_VALUE
    assert kwargs["labels"]["session_id"] == session_id
