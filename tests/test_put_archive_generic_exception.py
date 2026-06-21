import pytest
from unittest.mock import MagicMock, patch
from main import KernelManager

@pytest.fixture
def km():
    manager = KernelManager()
    manager.active_kernels = {}
    return manager

def test_put_archive_with_retry_generic_exception(km):
    """Tests that _put_archive_with_retry does NOT catch generic Exceptions."""
    session_id = "test_session"
    mock_container = MagicMock()

    # Mock put_archive to raise a generic Exception
    mock_container.put_archive.side_effect = Exception("Generic error")

    with patch.object(km, 'get_or_create_container') as mock_get_create:
        # Verify that the Exception is raised
        with pytest.raises(Exception) as excinfo:
            km._put_archive_with_retry(session_id, mock_container, "/path", b"data")

        assert str(excinfo.value) == "Generic error"

        # Verify get_or_create_container was NOT called (no retry)
        mock_get_create.assert_not_called()
