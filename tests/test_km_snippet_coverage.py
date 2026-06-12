import pytest
import asyncio
import time
from unittest.mock import MagicMock, patch, ANY
import docker
from main import KernelManager
import main

@pytest.fixture
def km():
    manager = KernelManager()
    manager.active_kernels = {}
    return manager

def test_put_archive_with_retry_not_found(km):
    """Tests that _put_archive_with_retry recovers from NotFound error."""
    session_id = "test_session"
    mock_container_old = MagicMock()
    mock_container_new = MagicMock()

    # First call to put_archive fails, second succeeds on new container
    mock_container_old.put_archive.side_effect = docker.errors.NotFound("Container not found")

    with patch.object(km, 'get_or_create_container', return_value=mock_container_new) as mock_get_create:
        params = main.ArchiveParams(
            session_id=session_id,
            path="/path",
            data=b"data",
            external_session_id=None
        )
        km._put_archive_with_retry(mock_container_old, params)

        # Verify get_or_create_container was called with force_refresh=True
        mock_get_create.assert_called_once_with(session_id, force_refresh=True, external_session_id=None)

        # Verify put_archive was called on the new container
        mock_container_new.put_archive.assert_called_once_with("/path", b"data")

def test_cleanup_sessions_directory_removal(km, tmp_path):
    """Tests that cleanup_sessions removes the session directory if it exists."""
    session_id = "test_session_dir"

    # Create a mock session directory
    internal_data_dir = tmp_path / "sessions"
    internal_data_dir.mkdir()
    session_dir = internal_data_dir / session_id
    session_dir.mkdir()

    # Ensure it's not empty
    (session_dir / "test_file.txt").write_text("hello")

    mock_container = MagicMock()
    km.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time() - (main.RCE_SESSION_TTL + 100)
    }

    with patch("main.RCE_DATA_DIR_INTERNAL", str(internal_data_dir)):
        km.cleanup_sessions()

        # Verify directory was removed
        assert not session_dir.exists()
        # Verify container was stopped
        mock_container.stop.assert_called_once()
        # Verify session was removed from active_kernels
        assert session_id not in km.active_kernels

@pytest.mark.asyncio
async def test_cleanup_loop_explicit_error_handler(km):
    """Tests the explicit error handler in cleanup_loop (Line 478)."""

    # We want to trigger the 'except Exception as e' in cleanup_loop
    # which wraps await asyncio.to_thread(self.cleanup_sessions)

    with patch("main.asyncio.to_thread", side_effect=Exception("Thread failure")):
        with patch("main.logger") as mock_logger:
            # Patch main.asyncio.sleep only to avoid global flakiness
            with patch("main.asyncio.sleep", side_effect=asyncio.CancelledError):
                try:
                    await km.cleanup_loop()
                except asyncio.CancelledError:
                    pass

                # Verify logger.error was called with the specific message
                mock_logger.error.assert_any_call("Error in cleanup loop: %s", ANY)

                # Specifically verify the exception message if possible
                args, _ = mock_logger.error.call_args
                assert "Error in cleanup loop" in args[0]
                assert "Thread failure" in str(args[1])

def test_cleanup_sessions_error_handling_explicit(km):
    """Tests the error handler in cleanup_sessions (Line 469)."""
    session_id = "test_session_error"
    mock_container = MagicMock()
    # Mock stop to raise an exception
    mock_container.stop.side_effect = Exception("Stop failed")

    km.active_kernels[session_id] = {
        "container": mock_container,
        "last_accessed": time.time() - (main.RCE_SESSION_TTL + 100)
    }

    with patch("main.logger") as mock_logger:
        km.cleanup_sessions()

        # Verify logger.error was called
        mock_logger.error.assert_called_with(
            "Error cleaning up session %s: %s", session_id, ANY
        )

        args, _ = mock_logger.error.call_args
        assert "Stop failed" in str(args[2])
