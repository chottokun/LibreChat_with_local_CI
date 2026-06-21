import pytest
from unittest.mock import MagicMock, patch, call, ANY
import docker
from main import KernelManager

@pytest.fixture
def km():
    manager = KernelManager()
    manager.active_kernels = {}
    return manager

def test_put_archive_success_first_try(km):
    session_id = "test_session"
    mock_container = MagicMock()

    with patch.object(km, 'get_or_create_container') as mock_get_create:
        km._put_archive_with_retry(session_id, mock_container, "/path", b"data")

        mock_container.put_archive.assert_called_once_with("/path", b"data")
        mock_get_create.assert_not_called()

def test_put_archive_success_second_try(km):
    session_id = "test_session"
    mock_container_1 = MagicMock()
    mock_container_2 = MagicMock()

    # First call fails, second succeeds
    mock_container_1.put_archive.side_effect = docker.errors.NotFound("Not found")

    with patch.object(km, 'get_or_create_container', return_value=mock_container_2) as mock_get_create:
        km._put_archive_with_retry(session_id, mock_container_1, "/path", b"data")

        assert mock_container_1.put_archive.call_count == 1
        assert mock_container_2.put_archive.call_count == 1
        mock_get_create.assert_called_once_with(session_id, force_refresh=True, external_session_id=None)

def test_put_archive_success_third_try(km):
    session_id = "test_session"
    mock_container_1 = MagicMock()
    mock_container_2 = MagicMock()
    mock_container_3 = MagicMock()

    mock_container_1.put_archive.side_effect = docker.errors.NotFound("Not found 1")
    mock_container_2.put_archive.side_effect = docker.errors.APIError("API Error 2")

    with patch.object(km, 'get_or_create_container', side_effect=[mock_container_2, mock_container_3]) as mock_get_create:
        km._put_archive_with_retry(session_id, mock_container_1, "/path", b"data")

        assert mock_container_1.put_archive.call_count == 1
        assert mock_container_2.put_archive.call_count == 1
        assert mock_container_3.put_archive.call_count == 1

        assert mock_get_create.call_count == 2
        mock_get_create.assert_has_calls([
            call(session_id, force_refresh=True, external_session_id=None),
            call(session_id, force_refresh=True, external_session_id=None)
        ])

def test_put_archive_exhausted_retries(km):
    session_id = "test_session"
    mock_container_1 = MagicMock()
    mock_container_2 = MagicMock()
    mock_container_3 = MagicMock()

    mock_container_1.put_archive.side_effect = docker.errors.NotFound("Fail 1")
    mock_container_2.put_archive.side_effect = docker.errors.NotFound("Fail 2")
    mock_container_3.put_archive.side_effect = docker.errors.NotFound("Fail 3")

    with patch.object(km, 'get_or_create_container', side_effect=[mock_container_2, mock_container_3]) as mock_get_create:
        with pytest.raises(docker.errors.NotFound, match="Fail 3"):
            km._put_archive_with_retry(session_id, mock_container_1, "/path", b"data")

        assert mock_container_1.put_archive.call_count == 1
        assert mock_container_2.put_archive.call_count == 1
        assert mock_container_3.put_archive.call_count == 1
        assert mock_get_create.call_count == 2

def test_put_archive_logging(km):
    session_id = "test_session_log"
    mock_container_1 = MagicMock()
    mock_container_2 = MagicMock()

    mock_container_1.put_archive.side_effect = docker.errors.NotFound("Log failure")

    with patch.object(km, 'get_or_create_container', return_value=mock_container_2):
        with patch("main.logger") as mock_logger:
            km._put_archive_with_retry(session_id, mock_container_1, "/path", b"data")

            # Verify warning was logged with correct arguments
            mock_logger.warning.assert_called_once_with(
                "Retry %d/%d: put_archive failed for session %s, refreshing container: %s",
                1, 3, session_id, ANY
            )

def test_put_archive_final_error_logging(km):
    session_id = "test_session_final_log"
    mock_container = MagicMock()
    mock_container.put_archive.side_effect = docker.errors.NotFound("Final failure")

    with patch.object(km, 'get_or_create_container', return_value=mock_container):
        with patch("main.logger") as mock_logger:
            with pytest.raises(docker.errors.NotFound):
                km._put_archive_with_retry(session_id, mock_container, "/path", b"data")

            # Verify error was logged on final failure
            mock_logger.error.assert_called_once_with(
                "Failed to put archive for session %s after %d attempts: %s",
                session_id, 3, ANY
            )
