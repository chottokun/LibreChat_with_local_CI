import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from unittest.mock import patch, MagicMock
import main
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

def test_upload_files_generic_exception_handling():
    """
    Test that a generic Exception in upload_files is caught and returned as a 500 error.
    """
    with patch.object(kernel_manager, 'upload_file', side_effect=Exception("Unexpected error")):
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "test-session"},
            files=[("files", ("test.txt", b"content"))]
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Unexpected error"

def test_upload_files_http_exception_propagation():
    """
    Test that an HTTPException in upload_files is propagated with its original status code.
    """
    with patch.object(kernel_manager, 'upload_file', side_effect=HTTPException(status_code=400, detail="Custom HTTP error")):
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "test-session"},
            files=[("files", ("test.txt", b"content"))]
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Custom HTTP error"

def test_upload_files_read_failure():
    """
    Test that a failure during file reading is caught and returned as a 500 error.
    """
    # Mock upload_file to prevent it from even being called.
    # We use a broader patch for UploadFile.read by targeting the one from starlette
    # which is what FastAPI uses under the hood.
    with patch.object(kernel_manager, 'resolve_session_id', return_value="fixed-session-id"), \
         patch.object(kernel_manager, 'upload_file'), \
         patch("starlette.datastructures.UploadFile.read", side_effect=Exception("Read failure")):

        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "test-session"},
            files=[("files", ("test.txt", b"content"))]
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Read failure"

def test_upload_files_session_resolution_error():
    """
    Test that an error during session resolution is caught and returned as a 500 error.
    """
    with patch.object(kernel_manager, 'resolve_session_id', side_effect=Exception("Resolution error")):
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "test-session"},
            files=[("files", ("test.txt", b"content"))]
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Resolution error"
