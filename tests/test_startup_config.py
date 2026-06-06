import os
import importlib
import pytest
import logging
from unittest.mock import patch, MagicMock

# Set API KEY before importing main to avoid collection error
os.environ["LIBRECHAT_CODE_API_KEY"] = "dummy-key-for-collection"
import main

@pytest.fixture(autouse=True)
def reset_env():
    # Store original environment, RCE_DATA_DIR_HOST, and the original kernel_manager instance
    orig_env = os.environ.copy()
    orig_host = getattr(main, 'RCE_DATA_DIR_HOST', None)
    orig_km = getattr(main, 'kernel_manager', None)
    yield
    # Restore
    os.environ.clear()
    os.environ.update(orig_env)
    main.RCE_DATA_DIR_HOST = orig_host
    # Reload main to ensure it's in a clean state for other tests
    importlib.reload(main)
    # Restore the original kernel_manager instance so that other tests' imports remain valid
    if orig_km is not None:
        main.kernel_manager = orig_km

def test_makedirs_exception_fallback(caplog):
    """Test that RCE_DATA_DIR_HOST falls back to None if os.makedirs raises an exception."""
    caplog.set_level(logging.WARNING)
    with patch.dict(os.environ, {
        "RCE_DATA_DIR_HOST": "/host/path",
        "LIBRECHAT_CODE_API_KEY": "test-key",
        "RCE_DATA_DIR_INTERNAL": "/internal/path"
    }), patch("os.makedirs") as mock_makedirs:

        mock_makedirs.side_effect = Exception("Permission denied")

        importlib.reload(main)

        assert main.RCE_DATA_DIR_HOST is None
        assert "Failed to initialize shared volume: Permission denied. Falling back to 'put_archive' mode." in caplog.text

def test_permission_error_fallback(caplog):
    """Test that RCE_DATA_DIR_HOST falls back to None if os.access returns False."""
    caplog.set_level(logging.WARNING)
    with patch.dict(os.environ, {
        "RCE_DATA_DIR_HOST": "/host/path",
        "LIBRECHAT_CODE_API_KEY": "test-key",
        "RCE_DATA_DIR_INTERNAL": "/internal/path"
    }), patch("os.makedirs"), \
        patch("os.access") as mock_access:

        mock_access.return_value = False

        importlib.reload(main)

        assert main.RCE_DATA_DIR_HOST is None
        assert "!!! PERMISSION ERROR !!!" in caplog.text
        assert "Falling back to 'put_archive' mode (slower, but works without host mounting)." in caplog.text

def test_happy_path_initialization(caplog):
    """Test that RCE_DATA_DIR_HOST is preserved if everything is correct."""
    caplog.set_level(logging.INFO)
    with patch.dict(os.environ, {
        "RCE_DATA_DIR_HOST": "/host/path",
        "LIBRECHAT_CODE_API_KEY": "test-key",
        "RCE_DATA_DIR_INTERNAL": "/internal/path"
    }), patch("os.makedirs"), \
        patch("os.access") as mock_access:

        mock_access.return_value = True

        importlib.reload(main)

        assert main.RCE_DATA_DIR_HOST == "/host/path"
        assert "Volume mounting enabled: /host/path -> /internal/path" in caplog.text
