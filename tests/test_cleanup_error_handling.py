import pytest
import time
from unittest.mock import MagicMock, patch
import main
from main import KernelManager

@pytest.fixture
def km():
    manager = KernelManager()
    manager.active_kernels = {}
    manager.nanoid_to_session = {}
    manager.session_to_nanoid = {}
    manager.file_id_map = {}
    return manager

def test_cleanup_sessions_continues_after_error(km, caplog):
    """
    Verify that if an error occurs while cleaning up one session,
    the cleanup process continues for other sessions.
    """
    # Force TTL to be small so everything is idle
    with patch("main.RCE_SESSION_TTL", 0):
        now = time.time()

        # Session 1: Will fail during stop
        sid1 = "session_fail"
        mock_container1 = MagicMock()
        mock_container1.stop.side_effect = Exception("Docker stop failed")
        km.active_kernels[sid1] = {
            "container": mock_container1,
            "last_accessed": now - 100
        }
        km.session_to_nanoid[sid1] = "nanoid1"
        km.nanoid_to_session["nanoid1"] = sid1
        km.file_id_map["nanoid1"] = {"f1": "file1.txt"}

        # Session 2: Will succeed
        sid2 = "session_success"
        mock_container2 = MagicMock()
        km.active_kernels[sid2] = {
            "container": mock_container2,
            "last_accessed": now - 100
        }
        km.session_to_nanoid[sid2] = "nanoid2"
        km.nanoid_to_session["nanoid2"] = sid2
        km.file_id_map["nanoid2"] = {"f2": "file2.txt"}

        # Execute
        km.cleanup_sessions()

        # Assertions

        # Verify error was logged in caplog
        assert f"Error cleaning up session {sid1}: Docker stop failed" in caplog.text

        # Verify Session 2 was also attempted (and succeeded)
        mock_container2.stop.assert_called_once()

        # Verify both are removed from active_kernels
        assert sid1 not in km.active_kernels
        assert sid2 not in km.active_kernels

        # Verify mappings are cleared for both
        assert sid1 not in km.session_to_nanoid
        assert "nanoid1" not in km.nanoid_to_session
        assert "nanoid1" not in km.file_id_map

        assert sid2 not in km.session_to_nanoid
        assert "nanoid2" not in km.nanoid_to_session
        assert "nanoid2" not in km.file_id_map

def test_cleanup_sessions_rmtree_error(km, caplog):
    """
    Verify that if shutil.rmtree fails (not ignored by ignore_errors), the cleanup continues.
    Note: The current code uses ignore_errors=True, but we can still mock it to raise
    or just test that the exception handling around the whole block works.
    """
    with patch("main.RCE_SESSION_TTL", 0):
        now = time.time()
        sid = "session_rmtree_fail"
        mock_container = MagicMock()

        km.active_kernels[sid] = {
            "container": mock_container,
            "last_accessed": now - 100
        }

        # We need to patch where shutil is used, which is in main.py
        with patch("main.RCE_DATA_DIR_INTERNAL", "/tmp/sessions"), \
             patch("os.path.exists", return_value=True), \
             patch("main.shutil.rmtree", side_effect=Exception("rmtree catastrophic failure")):

            km.cleanup_sessions()

            # Verify error log
            assert f"Error cleaning up session {sid}: rmtree catastrophic failure" in caplog.text

            # Since rmtree failed and it's before container.stop(), stop should NOT be called
            # if the exception was caught and we moved to next session.
            mock_container.stop.assert_not_called()

            # However, the session should still be removed from active_kernels
            # because pop happens BEFORE rmtree.
            assert sid not in km.active_kernels
