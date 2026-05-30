import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import os
from urllib.parse import quote
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

def test_download_session_file_path_params_success_standard_mode():
    """Test path-based download in Standard Mode (Docker API)."""
    session_id = "nanoid-session"
    file_id = "nanoid-file"
    real_session = "uuid-session"
    real_filename = "data.txt"

    with kernel_manager.lock:
        kernel_manager.nanoid_to_session[session_id] = real_session
        kernel_manager.file_id_map[session_id] = {file_id: real_filename}

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, 'download_file') as mock_download:

        mock_download.return_value = (b"file content", 12345.0)

        response = client.get(
            f"/api/files/code/download/{session_id}/{file_id}",
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.content == b"file content"
        assert "Content-Disposition" in response.headers
        assert f"filename=\"{real_filename}\"" in response.headers["Content-Disposition"]
        mock_download.assert_called_once_with(real_session, real_filename)

def test_download_session_file_alternate_routes():
    """Verify all path-based routes work."""
    routes = [
        "/api/files/code/download/s/f",
        "/download/s/f",
        "/run/download/s/f"
    ]

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, 'download_file') as mock_download:
        mock_download.return_value = (b"content", 0)

        for route in routes:
            response = client.get(route, headers={"X-API-Key": API_KEY})
            assert response.status_code == 200
            assert response.content == b"content"

def test_download_session_file_path_params_success_advanced_mode():
    """Test path-based download in Advanced Mode (Volume mapping)."""
    session_id = "nanoid-session"
    file_id = "nanoid-file"
    real_session = "uuid-session"
    real_filename = "data.txt"

    with kernel_manager.lock:
        kernel_manager.nanoid_to_session[session_id] = real_session
        kernel_manager.file_id_map[session_id] = {file_id: real_filename}

    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("main.RCE_DATA_DIR_INTERNAL", "/internal/path"), \
         patch("os.path.exists", return_value=True), \
         patch("main.FileResponse") as mock_file_response:

        mock_file_response.return_value = MagicMock()

        response = client.get(
            f"/download/{session_id}/{file_id}",
            headers={"X-API-Key": API_KEY}
        )

        # FastAPI's TestClient with FileResponse might return a 200 even if mock is used
        assert response.status_code == 200
        mock_file_response.assert_called_once()
        args, kwargs = mock_file_response.call_args
        assert kwargs["path"] == f"/internal/path/{real_session}/{real_filename}"

def test_download_file_query_params_success():
    """Test query-based download."""
    session_id = "test-session"
    filename = "test.txt"

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, 'download_file') as mock_download:

        mock_download.return_value = (b"query content", 12345.0)

        # Test /download
        response = client.get(
            "/download",
            params={"session_id": session_id, "filename": filename},
            headers={"X-API-Key": API_KEY}
        )
        assert response.status_code == 200
        assert response.content == b"query content"

        # Test /run/download
        response = client.get(
            "/run/download",
            params={"session_id": session_id, "filename": filename},
            headers={"X-API-Key": API_KEY}
        )
        assert response.status_code == 200
        assert response.content == b"query content"

        assert mock_download.call_count == 2

def test_download_csv_mime_type():
    """Test that .csv files get text/plain MIME type."""
    session_id = "session1"
    filename = "data.csv"

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, 'download_file') as mock_download:

        mock_download.return_value = (b"a,b,c", 12345.0)

        response = client.get(
            f"/run/download/{session_id}/{filename}",
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert "inline" in response.headers["Content-Disposition"]

def test_download_non_ascii_filename():
    """Test Content-Disposition for non-ASCII filenames."""
    session_id = "session1"
    filename = "テスト.txt"

    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, 'download_file') as mock_download:

        mock_download.return_value = (b"content", 12345.0)

        response = client.get(
            f"/download/{session_id}/{filename}",
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 200
        cd = response.headers["Content-Disposition"]
        assert "filename=\".txt\"" in cd  # ASCII fallback for "テスト.txt"
        # quote uses %E3%83%86%E3%82%B9%E3%83%88.txt
        expected_encoded = quote(filename)
        assert f"filename*=utf-8''{expected_encoded}" in cd

def test_download_unauthorized():
    """Test that download fails without valid API key."""
    response = client.get(
        "/download/session/file",
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401

def test_download_not_found_standard_mode():
    """Test 404 in Standard Mode."""
    with patch("main.RCE_DATA_DIR_HOST", None), \
         patch.object(kernel_manager, 'download_file') as mock_download:

        from fastapi import HTTPException
        mock_download.side_effect = HTTPException(status_code=404, detail="File not found")

        response = client.get(
            "/download/session/missing.txt",
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 404

def test_download_not_found_advanced_mode():
    """Test 404 in Advanced Mode."""
    with patch("main.RCE_DATA_DIR_HOST", "/host/path"), \
         patch("os.path.exists", return_value=False):

        response = client.get(
            "/download/session/missing.txt",
            headers={"X-API-Key": API_KEY}
        )

        assert response.status_code == 404
