import pytest
from unittest.mock import patch
import os
from main import KernelManager

@pytest.fixture
def kernel_manager():
    return KernelManager()

def test_prepare_volumes_disabled(kernel_manager):
    """
    Verifies that _prepare_volumes returns an empty dictionary
    when RCE_DATA_DIR_HOST is not set.
    """
    with patch("main.RCE_DATA_DIR_HOST", None):
        volumes = kernel_manager._prepare_volumes("test_session")
        assert volumes == {}

def test_prepare_volumes_enabled(kernel_manager):
    """
    Verifies that _prepare_volumes returns the correct volume mapping
    and ensures the internal session directory exists when RCE_DATA_DIR_HOST is set.
    """
    session_id = "test_session_123"
    host_base = "/host/data"
    internal_base = "/internal/data"

    with patch("main.RCE_DATA_DIR_HOST", host_base), \
         patch("main.RCE_DATA_DIR_INTERNAL", internal_base), \
         patch("pathlib.Path.mkdir") as mock_mkdir:

        volumes = kernel_manager._prepare_volumes(session_id)

        expected_host_path = os.path.join(host_base, session_id)

        assert volumes == {expected_host_path: {'bind': '/mnt/data', 'mode': 'rw'}}
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
