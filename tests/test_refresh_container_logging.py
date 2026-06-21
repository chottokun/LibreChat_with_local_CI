import pytest
import logging
import os
import time
from unittest.mock import MagicMock, patch

# Mock docker.from_env and set env vars before importing main to prevent side effects
with patch("docker.from_env") as mock_from_env:
    os.environ.setdefault("LIBRECHAT_CODE_API_KEY", "dummy-key")
    os.environ.setdefault("DISABLE_CODE_API_AUTH", "true")
    from main import KernelManager

@pytest.fixture
def kernel_manager():
    km = KernelManager()
    km.active_kernels = {}
    return km

def test_refresh_container_reload_exception_logs_and_recovers(kernel_manager, caplog):
    """
    Verifies that if container.reload() raises a generic Exception during get_or_create_container,
    it is logged, the session is removed from active_kernels, and it falls through to create a new container.
    """
    session_id = "reload_fail_session"
    mock_container = MagicMock()
    mock_container.reload.side_effect = Exception("Reload failed unexpectedly")

    # Pre-populate active_kernels
    kernel_manager.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time()
    }

    # Mock start_new_container_unlocked to avoid actual Docker calls and verify behavior
    new_container = MagicMock()

    def mock_start_new_unlocked(sid, external_session_id=None):
        # Verify that the old session was popped BEFORE trying to start a new one
        assert session_id not in kernel_manager.active_kernels
        return new_container

    kernel_manager.start_new_container_unlocked = MagicMock(side_effect=mock_start_new_unlocked)

    with caplog.at_level(logging.ERROR):
        # Execute with force_refresh=True to ensure reload() is called
        result = kernel_manager.get_or_create_container(session_id, force_refresh=True)

        # Verify logging
        assert f"Error refreshing container for session {session_id}" in caplog.text
        assert "Reload failed unexpectedly" in caplog.text

        # Verify session was popped (start_new_container_unlocked was called,
        # and result is the new container)
        assert result == new_container
        kernel_manager.start_new_container_unlocked.assert_called_once_with(session_id, None)

def test_refresh_container_start_exception_logs_and_recovers(kernel_manager, caplog):
    """
    Verifies that if container.start() raises a generic Exception during get_or_create_container,
    it is logged, the session is removed from active_kernels, and it falls through to create a new container.
    """
    session_id = "start_fail_session"
    mock_container = MagicMock()
    mock_container.status = "exited"
    # reload succeeds but start fails
    mock_container.reload.return_value = None
    mock_container.start.side_effect = Exception("Start failed unexpectedly")

    # Pre-populate active_kernels
    kernel_manager.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time()
    }

    # Mock start_new_container_unlocked
    new_container = MagicMock()

    def mock_start_new_unlocked(sid, external_session_id=None):
        # Verify that the old session was popped BEFORE trying to start a new one
        assert session_id not in kernel_manager.active_kernels
        return new_container

    kernel_manager.start_new_container_unlocked = MagicMock(side_effect=mock_start_new_unlocked)

    with caplog.at_level(logging.ERROR):
        # Execute with force_refresh=True to ensure we enter the refresh block
        result = kernel_manager.get_or_create_container(session_id, force_refresh=True)

        # Verify logging
        assert f"Error refreshing container for session {session_id}" in caplog.text
        assert "Start failed unexpectedly" in caplog.text

        # Verify session was popped and new container created
        assert result == new_container
        kernel_manager.start_new_container_unlocked.assert_called_once_with(session_id, None)
