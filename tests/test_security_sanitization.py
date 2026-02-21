import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import main
import os

def test_sanitize_id():
    from main import sanitize_id
    assert sanitize_id("safe-id_123") == "safe-id_123"
    assert sanitize_id("../../etc/passwd") == "etcpasswd"
    assert sanitize_id("session; drop table users") == "sessiondroptableusers"
    assert sanitize_id("id with spaces") == "idwithspaces"
    assert sanitize_id("") == ""

def test_path_traversal_blocked_upload():
    # Even with a mock kernel manager, we can check if it's called with sanitized ID
    with patch('main.kernel_manager') as mock_km:
        mock_km.resolve_session_id.side_effect = lambda x: x # Simple pass-through for mock

        client = TestClient(main.app)

        # Malicious entity_id
        response = client.post(
            "/upload",
            headers={"X-API-Key": main.API_KEY},
            data={"entity_id": "../../malicious"},
            files={"files": ("test.txt", b"content")}
        )

        assert response.status_code == 200
        # The ID passed to kernel_manager should be sanitized
        mock_km.resolve_session_id.assert_called_with("malicious")

def test_path_traversal_blocked_download():
    with patch('main.kernel_manager') as mock_km:
        mock_km.nanoid_to_session = {}
        mock_km.file_id_map = {}
        mock_km.download_file.return_value = (b"content", 123456789)
        mock_km.resolve_session_id.side_effect = lambda x: x

        client = TestClient(main.app)

        # Malicious session_id as query param to avoid path routing issues
        response = client.get(
            "/download",
            params={"session_id": "../../etc", "filename": "test.txt"},
            headers={"X-API-Key": main.API_KEY}
        )

        print(f"Response status: {response.status_code}")
        if response.status_code != 200:
            print(f"Response body: {response.text}")

        assert response.status_code == 200

        mock_km.download_file.assert_called()
        args, _ = mock_km.download_file.call_args
        assert args[0] == "etc"
