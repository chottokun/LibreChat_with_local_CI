import pytest
from fastapi.testclient import TestClient
from fastapi import UploadFile, HTTPException, Form
from unittest.mock import patch, MagicMock
from main import app, API_KEY, kernel_manager, upload_files
import os

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_kernel_manager():
    # Clear mappings before each test to ensure isolation
    with kernel_manager.lock:
        kernel_manager.active_kernels = {}
        kernel_manager.nanoid_to_session = {}
        kernel_manager.session_to_nanoid = {}
        kernel_manager.file_id_map = {}
    yield

def test_process_file_success():
    """Test the happy path of process_file within /upload."""
    with patch.object(kernel_manager, 'upload_file') as mock_upload:
        files = [("files", ("valid_file.txt", b"some content"))]
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "test-session"},
            files=files
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "success"
        assert any(f["filename"] == "valid_file.txt" for f in data["files"])

        # Verify kernel_manager.upload_file was called with expected arguments
        mock_upload.assert_called_once()
        args, kwargs = mock_upload.call_args
        assert args[1] == "valid_file.txt"
        assert args[2] == b"some content"
        assert kwargs["external_session_id"] == "test-session"

@pytest.mark.anyio
async def test_process_file_empty_filename_unit():
    """Test that process_file raises 400 for empty filename by calling the handler directly."""
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "" # Empty filename

    # We call the endpoint function directly to bypass TestClient's multipart encoding
    # and reach the inner process_file with our mock.
    # Passing raw strings for Form/Query parameters when calling the function directly.
    with pytest.raises(HTTPException) as excinfo:
        await upload_files(
            entity_id=None,
            session_id="test",
            files=[mock_file],
            file=None,
            session_id_query=None,
            key=API_KEY
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid filename"

@pytest.mark.anyio
async def test_process_file_none_filename_unit():
    """Test that process_file raises 400 for None filename."""
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = None # None filename

    with pytest.raises(HTTPException) as excinfo:
        await upload_files(
            entity_id=None,
            session_id="test",
            files=[mock_file],
            file=None,
            session_id_query=None,
            key=API_KEY
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid filename"

def test_process_file_invalid_basename():
    """Test that process_file raises 400 for a filename that has an empty basename."""
    # "folder/" has a basename of ""
    files = [("files", ("folder/", b"content"))]
    response = client.post(
        "/upload",
        headers={"X-API-Key": API_KEY},
        data={"session_id": "test-session"},
        files=files
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid filename"

def test_process_file_sanitizes_path():
    """Test that process_file uses only the basename of the provided filename."""
    with patch.object(kernel_manager, 'upload_file') as mock_upload:
        files = [("files", ("path/to/secret.txt", b"content"))]
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "test-session"},
            files=files
        )

        assert response.status_code == 200
        # Should only use "secret.txt"
        mock_upload.assert_called_once()
        assert mock_upload.call_args[0][1] == "secret.txt"

def test_process_file_multiple_files_concurrency():
    """Test that multiple files are processed correctly."""
    with patch.object(kernel_manager, 'upload_file') as mock_upload:
        files = [
            ("files", ("file1.txt", b"content1")),
            ("files", ("file2.txt", b"content2")),
            ("files", ("file3.txt", b"content3"))
        ]
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "test-session"},
            files=files
        )

        assert response.status_code == 200
        assert mock_upload.call_count == 3
        filenames = {call[0][1] for call in mock_upload.call_args_list}
        assert filenames == {"file1.txt", "file2.txt", "file3.txt"}
