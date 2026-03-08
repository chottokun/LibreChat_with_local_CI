import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import os
import io

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

def test_upload_success_entity_id():
    with patch.object(kernel_manager, 'upload_file') as mock_upload:
        # Pass multiple files with the same key "files"
        files = [
            ("files", ("test1.txt", b"content1")),
            ("files", ("test2.txt", b"content2"))
        ]
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"entity_id": "test-session"},
            files=files
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "success"
        assert len(data["files"]) == 2
        assert data["files"][0]["filename"] == "test1.txt"
        assert data["files"][1]["filename"] == "test2.txt"

        # Verify kernel_manager was called
        assert mock_upload.call_count == 2

        # Check if session mapping was created
        nanoid_session = data["session_id"]
        with kernel_manager.lock:
            assert nanoid_session in kernel_manager.nanoid_to_session

def test_upload_success_session_id_field():
    with patch.object(kernel_manager, 'upload_file') as mock_upload:
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "session-123"},
            files=[("file", ("file1.txt", b"data1"))]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "session-123"

        assert len(data["files"]) == 1
        assert data["filename"] == "file1.txt"
        mock_upload.assert_called_once()

def test_upload_success_query_param():
    with patch.object(kernel_manager, 'upload_file') as mock_upload:
        response = client.post(
            "/upload?session_id=query-session",
            headers={"X-API-Key": API_KEY},
            files=[("files", ("q.txt", b"q-data"))]
        )

        assert response.status_code == 200
        assert response.json()["session_id"] == "query-session"

def test_upload_no_session_id_generates_one():
    with patch.object(kernel_manager, 'upload_file') as mock_upload:
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            files=[("files", ("auto.txt", b"auto-content"))]
        )

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert len(data["session_id"]) == 21 # Nanoid size

def test_upload_no_files_fails():
    response = client.post(
        "/upload",
        headers={"X-API-Key": API_KEY},
        data={"entity_id": "some-id"}
    )
    assert response.status_code == 422
    assert "No files provided" in response.json()["detail"]

def test_upload_unauthorized():
    response = client.post(
        "/upload",
        headers={"X-API-Key": "wrong-key"},
        files=[("files", ("test.txt", b"content"))]
    )
    assert response.status_code == 401

def test_upload_priority_files_over_file():
    # Tests that 'files' takes priority over 'file' if both are present
    with patch.object(kernel_manager, 'upload_file') as mock_upload:
        files = [
            ("files", ("f1.txt", b"c1")),
            ("file", ("f2.txt", b"c2"))
        ]
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"entity_id": "mixed-id"},
            files=files
        )

        assert response.status_code == 200
        # According to current code: files = form.getlist("files") or form.getlist("file")
        # So only f1.txt should be uploaded.
        assert len(response.json()["files"]) == 1
        assert response.json()["files"][0]["filename"] == "f1.txt"
        assert mock_upload.call_count == 1

def test_upload_sanitizes_session_id():
    """Test that session ID is sanitized before use."""
    with patch.object(kernel_manager, 'upload_file') as mock_upload:
        # Use a session ID with characters that should be sanitized (removed)
        # sanitize_id allows alphanumeric, hyphen, and underscore
        dirty_session_id = "session_123!@#"
        expected_session_id = "session_123"

        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"entity_id": dirty_session_id},
            files=[("files", ("test.txt", b"content"))]
        )

        assert response.status_code == 200
        # The response session_id should be the sanitized one if it's new
        assert response.json()["session_id"] == expected_session_id

        # Verify kernel_manager.upload_file was called with the REAL (internal) session ID
        # Since expected_session_id was not already in nanoid_to_session,
        # it will be mapped to a new internal UUID.
        with kernel_manager.lock:
            real_id = kernel_manager.nanoid_to_session[expected_session_id]

        mock_upload.assert_called_once_with(real_id, "test.txt", b"content")

def test_upload_non_ascii_filename():
    """Test that non-ASCII (Japanese) filenames are handled correctly."""
    with patch.object(kernel_manager, 'upload_file') as mock_upload:
        # Japanese filename: テスト.txt
        japanese_filename = "テスト.txt"

        # We need to ensure the filename is properly encoded in the multipart request
        # fastapi/starlette handles this, but we should verify the API accepts it.
        files = [("files", (japanese_filename, b"japanese content"))]

        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"entity_id": "jap-session"},
            files=files
        )

        assert response.status_code == 200
        data = response.json()
        assert data["files"][0]["filename"] == japanese_filename

        with kernel_manager.lock:
            real_id = kernel_manager.nanoid_to_session["jap-session"]

        mock_upload.assert_called_once_with(real_id, japanese_filename, b"japanese content")
