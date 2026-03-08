import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from fastapi import HTTPException
from main import app, API_KEY, kernel_manager

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_kernel_manager():
    # Clear mappings before each test
    with kernel_manager.lock:
        kernel_manager.active_kernels = {}
        kernel_manager.nanoid_to_session = {}
        kernel_manager.session_to_nanoid = {}
        kernel_manager.file_id_map = {}
    yield

def test_upload_files_internal_error():
    """Test that a generic exception in upload_file returns a 500 error."""
    with patch.object(kernel_manager, 'upload_file', side_effect=Exception("Unexpected error")):
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"entity_id": "test-session"},
            files=[("files", ("test.txt", b"content"))]
        )
        assert response.status_code == 500
        assert "Unexpected error" in response.json()["detail"]

def test_upload_files_http_exception_propagation():
    """Test that an HTTPException in upload_file is propagated correctly."""
    with patch.object(kernel_manager, 'upload_file', side_effect=HTTPException(status_code=400, detail="Invalid file type")):
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"entity_id": "test-session"},
            files=[("files", ("test.txt", b"content"))]
        )
        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]
