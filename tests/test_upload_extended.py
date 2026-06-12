import pytest
import time
import main
import uuid
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app, API_KEY, kernel_manager

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_state():
    # Reset global state to ensure test isolation
    main.LAST_UPLOADED_SESSION_ID = None
    main.LAST_UPLOAD_TIME = 0
    # Clear kernel manager mappings
    with kernel_manager.lock:
        kernel_manager.active_kernels = {}
        kernel_manager.nanoid_to_session = {}
        kernel_manager.session_to_nanoid = {}
        kernel_manager.file_id_map = {}
    yield

def test_exec_fallback_to_last_upload():
    """
    Verify that the global LAST_UPLOADED_SESSION_ID set by /upload
    is correctly used as a fallback in /exec (L832-833).
    """
    with patch.object(kernel_manager, 'upload_file'):
        with patch.object(kernel_manager, 'execute_code') as mock_exec:
            with patch.object(kernel_manager, 'list_files', return_value=[]):
                mock_exec.return_value = {"stdout": "ok", "stderr": "", "exit_code": 0}

                # 1. Upload a file to establish a session
                session_id = "upload-session-fallback-test"
                client.post(
                    "/upload",
                    headers={"X-API-Key": API_KEY},
                    data={"session_id": session_id},
                    files=[("files", ("test.txt", b"hello"))]
                )

                assert main.LAST_UPLOADED_SESSION_ID == session_id

                # 2. Execute code without session_id - should fallback to session_id
                response = client.post(
                    "/exec",
                    headers={"X-API-Key": API_KEY},
                    json={"code": "print('hello')"}
                )

                assert response.status_code == 200
                assert response.json()["session_id"] == session_id
                mock_exec.assert_called_once()

def test_upload_multiple_files_one_invalid():
    """
    Verify that if any file in a multi-file upload has an invalid filename,
    the request returns a 400 error.
    """
    with patch.object(kernel_manager, 'upload_file'):
        files = [
            ("files", ("valid.txt", b"content")),
            ("files", ("/", b"invalid")) # Basename is empty, should trigger 400
        ]
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": "test-session"},
            files=files
        )
        assert response.status_code == 400
        assert "Invalid filename" in response.json()["detail"]

def test_upload_special_characters_session_id_mapping():
    """
    Verify that session IDs with special characters are correctly sanitized internally
    but the original ID is preserved in the mapping and response.
    """
    with patch.object(kernel_manager, 'upload_file') as mock_upload:
        special_sid = "session!@$ %^&*()"
        response = client.post(
            "/upload",
            headers={"X-API-Key": API_KEY},
            data={"session_id": special_sid},
            files=[("files", ("test.txt", b"content"))]
        )
        assert response.status_code == 200
        assert response.json()["session_id"] == special_sid

        # Verify internal sanitization and UUID mapping
        mock_upload.assert_called_once()
        real_sid = mock_upload.call_args[0][0]
        # Should be a valid UUID
        uuid.UUID(real_sid)

        # Check mapping from sanitized nanoid
        sanitized_sid = main.sanitize_id(special_sid)
        with kernel_manager.lock:
            assert kernel_manager.nanoid_to_session[sanitized_sid] == real_sid
            assert kernel_manager.session_to_nanoid[real_sid] == sanitized_sid
