import pytest
import time
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app, API_KEY, kernel_manager
from fastapi import UploadFile, Form
import main
import io

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_state():
    # Reset kernel_manager state
    with kernel_manager.lock:
        kernel_manager.active_kernels = {}
        kernel_manager.nanoid_to_session = {}
        kernel_manager.session_to_nanoid = {}
        kernel_manager.file_id_map = {}
    # Reset global variables
    main.LAST_UPLOADED_SESSION_ID = None
    main.LAST_UPLOAD_TIME = 0
    yield

def test_upload_duplicate_files_reuses_id():
    """Test that uploading the same file in the same session reuses the file_id."""
    with patch.object(kernel_manager, 'upload_file'):
        session_id = "test-session"
        filename = "duplicate.txt"
        content = b"some content"

        # First upload
        response1 = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": session_id},
            files=[("files", (filename, content))]
        )
        assert response1.status_code == 200
        file_id1 = response1.json()["files"][0]["fileId"]

        # Second upload of the same file
        response2 = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": session_id},
            files=[("files", (filename, content))]
        )
        assert response2.status_code == 200
        file_id2 = response2.json()["files"][0]["fileId"]

        assert file_id1 == file_id2

def test_upload_invalid_filename_empty():
    """Test that an empty filename (or one that becomes empty after basename) raises a 400 error."""
    with patch.object(kernel_manager, 'upload_file'):
        # Testing line 847: filename is not empty, but basename(filename) IS empty
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "test-session"},
            files=[("files", ("/", b"content"))]
        )
        assert response.status_code == 400
        assert "Invalid filename" in response.json()["detail"]

@pytest.mark.anyio
async def test_upload_invalid_filename_none():
    """Specifically test line 843 by calling the internal process_file with f.filename=None."""
    # We need to reach line 843. FastAPI's UploadFile normally ensures filename is a string.
    # But the code has a check for it.
    from main import upload_files

    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = None

    # We call the endpoint function directly.
    # We must provide strings for entity_id/session_id to avoid the 'Form' object issues in unit tests
    with pytest.raises(main.HTTPException) as excinfo:
        await upload_files(entity_id="test-session", files=[mock_file], key=API_KEY)

    assert excinfo.value.status_code == 400
    assert "Invalid filename" in excinfo.value.detail

def test_upload_updates_global_state():
    """Test that successful upload updates LAST_UPLOADED_SESSION_ID and LAST_UPLOAD_TIME."""
    with patch.object(kernel_manager, 'upload_file'):
        session_id = "global-test-session"

        # Before upload
        assert main.LAST_UPLOADED_SESSION_ID is None
        assert main.LAST_UPLOAD_TIME == 0

        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": session_id},
            files=[("files", ("test.txt", b"content"))]
        )
        assert response.status_code == 200

        # After upload
        assert main.LAST_UPLOADED_SESSION_ID == session_id
        assert main.LAST_UPLOAD_TIME > 0
        assert time.time() - main.LAST_UPLOAD_TIME < 5

def test_upload_generic_exception_handling():
    """Test that a generic exception during upload returns a 500 error."""
    with patch.object(kernel_manager, 'upload_file', side_effect=Exception("Unexpected error")):
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "error-session"},
            files=[("files", ("test.txt", b"content"))]
        )
        assert response.status_code == 500
        assert "Unexpected error" in response.json()["detail"]

def test_upload_kernel_manager_mock_fallback():
    """Test the fallback branch when kernel_manager is a MagicMock."""
    mock_km = MagicMock(spec=main.KernelManager)
    # Configure the mock to behave like the real KM enough to pass the early stages
    mock_km.resolve_session_id.return_value = "internal-uuid"
    mock_km.lock = MagicMock()
    mock_km.file_id_map = {}

    with patch("main.kernel_manager", mock_km):
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "mock-session"},
            files=[("files", ("test.txt", b"content"))]
        )
        # It should hit lines 834-837
        assert response.status_code == 200
        mock_km.resolve_session_id.assert_called()
        # Ensure it didn't call get_or_create_session_mapping (which is in the 'else' branch)
        mock_km.get_or_create_session_mapping.assert_not_called()
