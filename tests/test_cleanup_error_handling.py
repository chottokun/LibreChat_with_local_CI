import pytest
import asyncio
import time
from unittest.mock import MagicMock, patch
import main
from main import KernelManager

@pytest.fixture
def km():
    manager = KernelManager()
    manager.active_kernels = {}
    return manager

def test_cleanup_sessions_error_handling(km):
    """Test that cleanup_sessions handles errors during container stop."""
    session_id = "test_session"
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
            "Error cleaning up session %s: %s", session_id, mock_container.stop.side_effect
        )

        # Since pop happens BEFORE container.stop, the session IS removed from active_kernels even if stop fails.
        assert session_id not in km.active_kernels

@pytest.mark.asyncio
async def test_cleanup_loop_error_handling(km):
    """Test that cleanup_loop handles errors from to_thread(cleanup_sessions)."""

    # Mock cleanup_sessions to raise an exception
    with patch.object(km, "cleanup_sessions", side_effect=Exception("Thread execution failed")):
        with patch("main.logger") as mock_logger:
            # Mock asyncio.sleep to raise CancelledError to break the loop
            with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
                try:
                    await km.cleanup_loop()
                except asyncio.CancelledError:
                    pass

                # Verify logger.error was called for the loop error
                mock_logger.error.assert_any_call("Error in cleanup loop: %s", km.cleanup_sessions.side_effect)

def test_cleanup_sessions_continues_after_error(km):
    """Test that cleanup_sessions continues to next session if one fails."""
    s1 = "session1"
    s2 = "session2"

    c1 = MagicMock()
    c1.stop.side_effect = Exception("Stop 1 failed")
    c2 = MagicMock()

    now = time.time()
    km.active_kernels[s1] = {"container": c1, "last_accessed": now - (main.RCE_SESSION_TTL + 100)}
    km.active_kernels[s2] = {"container": c2, "last_accessed": now - (main.RCE_SESSION_TTL + 100)}

    with patch("main.logger") as mock_logger:
        km.cleanup_sessions()

        # Both should be popped
        assert s1 not in km.active_kernels
        assert s2 not in km.active_kernels

        # c1.stop was called and failed
        c1.stop.assert_called_once()
        # c2.stop should still be called
        c2.stop.assert_called_once()

        # Error for s1 should be logged
        mock_logger.error.assert_any_call("Error cleaning up session %s: %s", s1, c1.stop.side_effect)
