import pytest
import io
import tarfile
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
import main
from main import KernelManager

@pytest.fixture(autouse=True)
def mock_docker_client():
    """Replace main.DOCKER_CLIENT with a MagicMock for each test."""
    mock_client = MagicMock()
    original = main.DOCKER_CLIENT
    main.DOCKER_CLIENT = mock_client
    yield mock_client
    main.DOCKER_CLIENT = original

@pytest.fixture
def kernel_manager():
    km = KernelManager()
    km.active_kernels = {} # Clear it for each test
    return km

def test_download_file_docker_extractfile_returns_none(kernel_manager):
    """Test when tar.extractfile returns None (e.g., if member is a directory)."""
    session_id = "test_session"
    filename = "test_dir"
    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    # Create a tar stream where the first member is a directory
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode='w') as tar:
        tar_info = tarfile.TarInfo(name=filename)
        tar_info.type = tarfile.DIRTYPE
        tar.addfile(tar_info)

    mock_container.get_archive.return_value = ([tar_stream.getvalue()], {"mtime": 12345.0})

    with patch("main.RCE_DATA_DIR_HOST", None):
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.download_file(session_id, filename)
        assert excinfo.value.status_code == 404
        assert excinfo.value.detail == "File not found"

def test_download_file_docker_malformed_tar(kernel_manager):
    """Test when the bits returned by get_archive are not a valid tar archive."""
    session_id = "test_session"
    filename = "test.txt"
    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    # Malformed tar bits
    malformed_bits = [b"this is not a tar file"]
    mock_container.get_archive.return_value = (malformed_bits, {"mtime": 12345.0})

    with patch("main.RCE_DATA_DIR_HOST", None):
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.download_file(session_id, filename)
        assert excinfo.value.status_code == 404
        assert excinfo.value.detail == "File not found"

def test_download_file_docker_generator_failure(kernel_manager):
    """Test when the generator returned by get_archive raises an exception."""
    session_id = "test_session"
    filename = "test.txt"
    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    def failing_generator():
        yield b"partial bits"
        raise Exception("Stream failure")

    mock_container.get_archive.return_value = (failing_generator(), {"mtime": 12345.0})

    with patch("main.RCE_DATA_DIR_HOST", None):
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.download_file(session_id, filename)
        assert excinfo.value.status_code == 404
        assert excinfo.value.detail == "File not found"

def test_download_file_docker_unexpected_error_during_processing(kernel_manager):
    """Test any other unexpected error during tar processing."""
    session_id = "test_session"
    filename = "test.txt"
    mock_container = MagicMock()
    kernel_manager.get_or_create_container = MagicMock(return_value=mock_container)

    # Setup a valid tar but then mock tarfile.open to fail
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode='w') as tar:
        tar_info = tarfile.TarInfo(name=filename)
        tar_info.size = 0
        tar.addfile(tar_info, io.BytesIO(b""))

    mock_container.get_archive.return_value = ([tar_stream.getvalue()], {"mtime": 12345.0})

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch("tarfile.open", side_effect=RuntimeError("Unexpected tar error")):
        with pytest.raises(HTTPException) as excinfo:
            kernel_manager.download_file(session_id, filename)
        assert excinfo.value.status_code == 404
        assert excinfo.value.detail == "File not found"

from fastapi.testclient import TestClient
from main import app, API_KEY

client = TestClient(app)

@patch("main.kernel_manager.download_file")
def test_api_download_file_not_found(mock_download):
    """Test that the /download endpoint returns 404 when download_file raises HTTPException(404)."""
    mock_download.side_effect = HTTPException(status_code=404, detail="File not found")

    response = client.get(
        "/download",
        params={"session_id": "test_session", "filename": "missing.txt"},
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "File not found"

@patch("main.kernel_manager.download_file")
def test_api_download_session_file_not_found(mock_download):
    """Test that the /api/files/code/download/ endpoint returns 404 when download_file raises HTTPException(404)."""
    mock_download.side_effect = HTTPException(status_code=404, detail="File not found")

    response = client.get(
        "/api/files/code/download/test_session/missing.txt",
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "File not found"

@patch("main.kernel_manager.download_file")
def test_api_download_file_internal_error(mock_download):
    """Test that the /download endpoint returns 500 when download_file raises an unexpected Exception."""
    mock_download.side_effect = Exception("Unexpected internal error")

    # We use raise_server_exceptions=False to let the TestClient return a 500 instead of raising.
    local_client = TestClient(app, raise_server_exceptions=False)

    response = local_client.get(
        "/download",
        params={"session_id": "test_session", "filename": "error.txt"},
        headers={"X-API-Key": API_KEY}
    )

    assert response.status_code == 500
