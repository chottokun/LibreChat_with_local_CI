import pytest
import time
import asyncio
from unittest.mock import MagicMock, patch, call
import main
from main import KernelManager

@pytest.fixture
def kernel_manager():
    km = KernelManager()
    km.active_kernels = {}
    km.nanoid_to_session = {}
    km.session_to_nanoid = {}
    km.file_id_map = {}
    return km

def test_cleanup_sessions_expired(kernel_manager):
    # Setup
    now = 1000.0
    ttl = 100.0
    session_id_expired = "expired_session"
    session_id_active = "active_session"

    mock_container_expired = MagicMock()
    mock_container_active = MagicMock()

    with patch("time.time", return_value=now), \
         patch("main.RCE_SESSION_TTL", ttl), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/tmp/sessions"), \
         patch("os.path.exists", return_value=True), \
         patch("shutil.rmtree") as mock_rmtree:

        kernel_manager.active_kernels = {
            session_id_expired: {
                "container": mock_container_expired,
                "last_accessed": now - ttl - 1  # Expired
            },
            session_id_active: {
                "container": mock_container_active,
                "last_accessed": now - ttl + 1  # Active
            }
        }

        # Add some mappings to be cleared
        nanoid_expired = "nanoid_expired"
        kernel_manager.session_to_nanoid[session_id_expired] = nanoid_expired
        kernel_manager.nanoid_to_session[nanoid_expired] = session_id_expired
        kernel_manager.file_id_map[nanoid_expired] = {"file1": "path1"}

        nanoid_active = "nanoid_active"
        kernel_manager.session_to_nanoid[session_id_active] = nanoid_active
        kernel_manager.nanoid_to_session[nanoid_active] = session_id_active
        kernel_manager.file_id_map[nanoid_active] = {"file2": "path2"}

        # Execute
        kernel_manager.cleanup_sessions()

        # Assertions
        assert session_id_expired not in kernel_manager.active_kernels
        assert session_id_active in kernel_manager.active_kernels

        # Mapping assertions
        assert nanoid_expired not in kernel_manager.nanoid_to_session
        assert session_id_expired not in kernel_manager.session_to_nanoid
        assert nanoid_expired not in kernel_manager.file_id_map

        assert nanoid_active in kernel_manager.nanoid_to_session
        assert session_id_active in kernel_manager.session_to_nanoid
        assert nanoid_active in kernel_manager.file_id_map

        # Container stop assertion
        mock_container_expired.stop.assert_called_once_with(timeout=5)
        mock_container_active.stop.assert_not_called()

        # Directory removal assertion
        mock_rmtree.assert_called_once_with("/tmp/sessions/expired_session", ignore_errors=True)

def test_cleanup_sessions_exception_handling(kernel_manager):
    # Setup: two expired sessions, first one fails during cleanup
    now = 1000.0
    ttl = 100.0
    s1 = "session1"
    s2 = "session2"

    mock_c1 = MagicMock()
    mock_c1.stop.side_effect = Exception("Stop failed")
    mock_c2 = MagicMock()

    with patch("time.time", return_value=now), \
         patch("main.RCE_SESSION_TTL", ttl), \
         patch("main.RCE_DATA_DIR_INTERNAL", None), \
         patch("main.logger") as mock_logger:

        kernel_manager.active_kernels = {
            s1: {"container": mock_c1, "last_accessed": now - ttl - 10},
            s2: {"container": mock_c2, "last_accessed": now - ttl - 10}
        }

        # Execute
        kernel_manager.cleanup_sessions()

        # Assertions
        assert s1 not in kernel_manager.active_kernels
        assert s2 not in kernel_manager.active_kernels
        mock_c1.stop.assert_called_once()
        mock_c2.stop.assert_called_once()

        # Error should be logged for s1
        mock_logger.error.assert_called()
        any_s1_error = any(s1 in str(call) for call in mock_logger.error.call_args_list)
        assert any_s1_error

@pytest.mark.anyio
async def test_cleanup_loop_runs_and_handles_errors():
    km = KernelManager()

    # We want to test that it calls cleanup_sessions and handles errors.
    # We'll mock asyncio.sleep to raise CancelledError after a few calls to stop the loop.

    with patch.object(km, "cleanup_sessions") as mock_cleanup, \
         patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]) as mock_sleep, \
         patch("main.logger") as mock_logger:

        # Trigger an error in the first call to cleanup_sessions
        mock_cleanup.side_effect = [Exception("Cleanup failed"), None]

        try:
            await km.cleanup_loop()
        except asyncio.CancelledError:
            pass

        # Assertions
        assert mock_cleanup.call_count >= 1
        # Error should be logged
        mock_logger.error.assert_called()
        any_loop_error = any("Error in cleanup loop" in str(call) for call in mock_logger.error.call_args_list)
        assert any_loop_error

        # Check sleep was called (at least once before cancellation)
        mock_sleep.assert_called()
