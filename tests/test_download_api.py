import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import os
import tempfile
import shutil

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

def test_download_file_query_success_standard_mode():
    """Tests /download with query params in Standard Mode (Docker get_archive)."""
    # Mock RCE_DATA_DIR_HOST to None for standard mode
    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, 'download_file') as mock_download:

        file_content = b"fake file content"
        mock_download.return_value = (file_content, 123456789.0)

        response = client.get(
            "/download",
            params={"session_id": "test-session", "filename": "test.txt"},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.content == file_content
        assert "attachment" in response.headers["content-disposition"]
        assert "test.txt" in response.headers["content-disposition"]
        mock_download.assert_called_once_with("test-session", "test.txt")

def test_run_download_query_success_standard_mode():
    """Tests /run/download with query params."""
    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, 'download_file') as mock_download:

        file_content = b"run download content"
        mock_download.return_value = (file_content, 123456789.0)

        response = client.get(
            "/run/download",
            params={"session_id": "test-session", "filename": "run.txt"},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.content == file_content
        mock_download.assert_called_once_with("test-session", "run.txt")

def test_download_file_query_success_advanced_mode(tmp_path):
    """Tests /download with query params in Advanced Mode (Volume mount)."""
    # Setup a fake internal directory
    internal_dir = tmp_path / "sessions"
    session_id = "test-session-advanced"
    session_dir = internal_dir / session_id
    session_dir.mkdir(parents=True)

    file_name = "advanced.txt"
    file_path = session_dir / file_name
    file_content = b"advanced mode content"
    file_path.write_bytes(file_content)

    with patch("main.RCE_DATA_DIR_HOST", "/fake/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", str(internal_dir)):

        response = client.get(
            "/download",
            params={"session_id": session_id, "filename": file_name},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.content == file_content

def test_download_file_query_unauthorized():
    """Tests /download with invalid API key."""
    response = client.get(
        "/download",
        params={"session_id": "test", "filename": "test.txt"},
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401

def test_download_file_query_missing_params():
    """Tests /download with missing required query parameters."""
    # Missing filename
    response = client.get(
        "/download",
        params={"session_id": "test"},
        headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 422

    # Missing session_id
    response = client.get(
        "/download",
        params={"filename": "test.txt"},
        headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 422

def test_download_file_query_not_found():
    """Tests /download when file does not exist (Standard Mode)."""
    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, 'download_file') as mock_download:

        from fastapi import HTTPException
        mock_download.side_effect = HTTPException(status_code=404, detail="File not found")

        response = client.get(
            "/download",
            params={"session_id": "test-session", "filename": "missing.txt"},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 404

def test_download_file_query_sanitization():
    """Tests that session_id and filename are sanitized."""
    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, 'download_file') as mock_download:

        mock_download.return_value = (b"content", 123.0)

        # Path traversal attempt in session_id
        response = client.get(
            "/download",
            params={"session_id": "../../etc", "filename": "test.txt"},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        # "etc" is the sanitized version of "../../etc"
        mock_download.assert_called_with("etc", "test.txt")

        mock_download.reset_mock()

        # Path traversal attempt in filename
        response = client.get(
            "/download",
            params={"session_id": "test-session", "filename": "../../../secret.txt"},
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        # "secret.txt" is the base name of "../../../secret.txt"
        mock_download.assert_called_with("test-session", "secret.txt")
