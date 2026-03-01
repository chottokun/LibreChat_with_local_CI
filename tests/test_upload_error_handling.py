import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from unittest.mock import patch
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

def test_upload_files_generic_exception():
    """
    Test that a generic Exception in kernel_manager.upload_file
    results in a 500 status code.
    """
    with patch.object(kernel_manager, 'upload_file', side_effect=Exception("Test Exception")):
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "test-session"},
            files=[("files", ("test.txt", b"content"))]
        )

        assert response.status_code == 500
        assert response.json()["detail"] == "Test Exception"

def test_upload_files_http_exception():
    """
    Test that an HTTPException in kernel_manager.upload_file
    is re-raised correctly.
    """
    with patch.object(kernel_manager, 'upload_file', side_effect=HTTPException(status_code=400, detail="Bad Request")):
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "test-session"},
            files=[("files", ("test.txt", b"content"))]
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Bad Request"
