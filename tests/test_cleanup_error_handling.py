import sys
import time
import pytest
import logging
from unittest.mock import MagicMock, patch
import docker

# Ensure main is imported with mocks
mock_docker_client = MagicMock()
with patch("docker.from_env", return_value=mock_docker_client):
    import main
    from main import KernelManager

@pytest.fixture(autouse=True)
def cleanup_mocks():
    mock_docker_client.containers.run.reset_mock()
    mock_docker_client.containers.run.side_effect = None
    mock_docker_client.containers.list.reset_mock()
    mock_docker_client.containers.list.side_effect = None
    # Reset main.DOCKER_CLIENT to our mock just in case
    main.DOCKER_CLIENT = mock_docker_client

@pytest.fixture
def km():
    manager = KernelManager()
    manager.active_kernels = {}
    return manager

def test_cleanup_sessions_container_stop_failure(km, caplog):
    """Test that cleanup_sessions handles container.stop() failure gracefully."""
    session_id = "failing_session"
    mock_container = MagicMock()
    # Mock container.stop to raise an exception
    mock_container.stop.side_effect = Exception("Docker stop failed")

    # Use main.RCE_SESSION_TTL to ensure it's older than TTL
    km.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time() - (main.RCE_SESSION_TTL + 400)
    }

    # Execute
    with caplog.at_level(logging.ERROR):
        km.cleanup_sessions()

    # Assert
    # The session should still be removed from active_kernels because pop is called before stop
    assert session_id not in km.active_kernels
    assert f"Error cleaning up session {session_id}: Docker stop failed" in caplog.text
    mock_container.stop.assert_called_once()

def test_cleanup_sessions_multiple_sessions_one_fails(km, caplog):
    """Test that a failure in one session cleanup doesn't prevent others from being cleaned up."""
    # Session 1: Fails to stop
    s1 = "session_fail"
    c1 = MagicMock()
    c1.stop.side_effect = Exception("Stop failed for s1")

    # Session 2: Succeeds to stop
    s2 = "session_success"
    c2 = MagicMock()

    now = time.time()
    # Ensure both are older than TTL
    expired_time = now - (main.RCE_SESSION_TTL + 400)
    km.active_kernels[s1] = {"container": c1, "last_accessed": expired_time}
    km.active_kernels[s2] = {"container": c2, "last_accessed": expired_time}

    # Execute
    with caplog.at_level(logging.ERROR):
        km.cleanup_sessions()

    # Assert
    assert s1 not in km.active_kernels
    assert s2 not in km.active_kernels
    c1.stop.assert_called_once()
    c2.stop.assert_called_once()
    assert f"Error cleaning up session {s1}: Stop failed for s1" in caplog.text

def test_cleanup_sessions_shutil_rmtree_failure(km, caplog):
    """Test that cleanup_sessions handles shutil.rmtree failure if it happens."""
    session_id = "test_rmtree_fail"
    mock_container = MagicMock()

    km.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time() - (main.RCE_SESSION_TTL + 400)
    }

    # Mock os.path.exists and shutil.rmtree
    with patch("main.os.path.exists", return_value=True), \
         patch("main.shutil.rmtree", side_effect=Exception("rmtree failed")) as mock_rmtree, \
         caplog.at_level(logging.ERROR):

        # Execute
        km.cleanup_sessions()

        # Assert
        assert session_id not in km.active_kernels
        # Note: In the code, container.stop is AFTER shutil.rmtree.
        # If shutil.rmtree raises an exception, container.stop won't be called for that session.
        mock_container.stop.assert_not_called()
        assert f"Error cleaning up session {session_id}: rmtree failed" in caplog.text

def test_cleanup_sessions_id_mapping_cleanup(km):
    """Test that ID mappings are cleaned up even if stop fails."""
    session_id = "mapped_session"
    nanoid_session = "nanoid123"
    mock_container = MagicMock()
    mock_container.stop.side_effect = Exception("Stop failed")

    km.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time() - (main.RCE_SESSION_TTL + 400)
    }
    km.session_to_nanoid[session_id] = nanoid_session
    km.nanoid_to_session[nanoid_session] = session_id
    km.file_id_map[nanoid_session] = {"file1": "data.txt"}

    # Execute
    km.cleanup_sessions()

    # Assert
    assert session_id not in km.active_kernels
    assert session_id not in km.session_to_nanoid
    assert nanoid_session not in km.nanoid_to_session
    assert nanoid_session not in km.file_id_map
